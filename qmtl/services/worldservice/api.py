from __future__ import annotations

import asyncio
import inspect
import logging
from contextlib import asynccontextmanager
import contextlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, cast

import redis.asyncio as redis
from fastapi import FastAPI

from qmtl.foundation.config import (
    DeploymentProfile,
    RiskHubConfig,
    find_config_file,
    load_config,
)

from .controlbus_producer import ControlBusProducer
from .controlbus_consumer import RiskHubControlBusConsumer
from .config import WorldServiceServerConfig
from .routers import (
    create_activation_router,
    create_allocations_router,
    create_bindings_router,
    create_evaluation_runs_router,
    create_live_monitoring_router,
    create_observability_router,
    create_risk_hub_router,
    create_policies_router,
    create_rebalancing_router,
    create_validations_router,
    create_worlds_router,
)
from .schemas import (
    ApplyAck,
    ApplyPlan,
    ApplyRequest,
    ApplyResponse,
    EvaluateRequest,
    PolicyRequest,
    World,
)
from .services import WorldService
from .storage import PersistentStorage, Storage
from .risk_hub import RiskSignalHub
from .blob_store import build_blob_store


logger = logging.getLogger(__name__)


@dataclass
class StorageHandle:
    """Container pairing a storage instance with an optional shutdown hook."""

    storage: Storage
    shutdown: Callable[[], Awaitable[None]] | None = None


def _coerce_storage_handle(result: Storage | StorageHandle) -> StorageHandle:
    if isinstance(result, StorageHandle):
        return result
    return StorageHandle(storage=result)


async def _maybe_await(value: Any) -> None:
    if inspect.isawaitable(value):
        await value


def _bind_risk_hub_backend(
    hub: RiskSignalHub | None, storage: Any, *, cache_ttl: int | None = None
) -> None:
    if hub is None:
        return
    try:
        if isinstance(storage, PersistentStorage):
            hub.bind_repository(storage.risk_snapshots)
            redis_client = getattr(storage, "_redis", None)
            if redis_client is not None:
                hub.bind_cache(redis_client, ttl=cache_ttl)
    except Exception:  # pragma: no cover - defensive binding
        logger.exception("Failed to bind risk hub repository")


def _config_storage_factory(config: WorldServiceServerConfig) -> Callable[[], Awaitable[StorageHandle]]:
    if not config.redis:
        raise ValueError("WorldService configuration requires a Redis DSN")

    async def _factory() -> StorageHandle:
        redis_client = redis.from_url(config.redis, decode_responses=True)
        storage = cast(Storage, await PersistentStorage.create(db_dsn=config.dsn, redis_client=redis_client))

        async def _shutdown() -> None:
            close = getattr(storage, "close", None)
            if close is not None:
                await _maybe_await(close())
            try:
                if hasattr(redis_client, "aclose"):
                    await _maybe_await(redis_client.aclose())
                elif hasattr(redis_client, "close"):
                    await _maybe_await(redis_client.close())
            except Exception:  # pragma: no cover - defensive cleanup
                logger.exception("Failed to close WorldService Redis client")
            pool = getattr(redis_client, "connection_pool", None)
            if pool is not None:
                disconnect = getattr(pool, "disconnect", None)
                if disconnect is not None:
                    await _maybe_await(disconnect())

        return StorageHandle(storage=storage, shutdown=_shutdown)

    return _factory


def _enforce_persistent_storage(
    storage: Storage | StorageHandle, *, profile: DeploymentProfile
) -> None:
    instance = storage.storage if isinstance(storage, StorageHandle) else storage
    if profile is not DeploymentProfile.PROD:
        return
    if isinstance(instance, Storage) and not isinstance(instance, PersistentStorage):
        raise RuntimeError(
            "Prod profile requires PersistentStorage; in-memory storage is disabled"
        )


def _coerce_profile(value: DeploymentProfile | str | None) -> DeploymentProfile | None:
    if value is None:
        return None
    if isinstance(value, DeploymentProfile):
        return value
    return DeploymentProfile(value.lower())


def _resolve_inline_threshold(cfg: RiskHubConfig | None) -> int | None:
    if cfg is None:
        return None
    if cfg.inline_cov_threshold is not None:
        return cfg.inline_cov_threshold
    return cfg.blob_store.inline_cov_threshold


def _build_hub_blob_store(
    cfg: RiskHubConfig | None,
    *,
    redis_url: str | None = None,
    redis_client: Any | None = None,
    profile: DeploymentProfile | None = None,
) -> Any | None:
    if cfg is None:
        return None
    if profile is not None and profile is not DeploymentProfile.PROD:
        # Dev: keep everything inline/fakeredis; no persistent/offload store
        return None
    try:
        client = redis_client
        if client is not None:
            setter = getattr(client, "set", None)
            if asyncio.iscoroutinefunction(setter):
                # Async Redis clients are not compatible with the sync blob store interface.
                # Fall back to DSN-based sync client construction.
                client = None
        return build_blob_store(
            store_type=cfg.blob_store.type,
            base_dir=cfg.blob_store.base_dir,
            bucket=cfg.blob_store.bucket,
            prefix=cfg.blob_store.prefix,
            redis_client=client,
            redis_dsn=redis_url,
            redis_prefix=cfg.blob_store.redis_prefix,
            cache_ttl=cfg.blob_store.cache_ttl,
        )
    except Exception:  # pragma: no cover - defensive fallback
        logger.exception("Failed to build risk hub blob store from config")
        return None


def _load_server_config(
    config: WorldServiceServerConfig | None,
    *,
    config_path: str | Path | None = None,
) -> tuple[WorldServiceServerConfig, DeploymentProfile, RiskHubConfig | None]:
    if config is not None:
        return config, DeploymentProfile.DEV, None

    resolved_path: str | None
    if config_path is not None:
        candidate = Path(config_path)
        if not candidate.is_file():
            raise RuntimeError(
                "WorldService configuration file not found. Provide --config, pass config_path to create_app, or create qmtl.yml in the working directory."
            )
        resolved_path = str(candidate)
    else:
        resolved_path = find_config_file()
        if resolved_path is None:
            raise RuntimeError(
                "WorldService configuration file not found. Provide --config, pass config_path to create_app, or create qmtl.yml in the working directory."
            )

    unified = load_config(resolved_path)
    server_config = unified.worldservice.server
    if server_config is None:
        raise RuntimeError(
            "WorldService configuration missing 'worldservice' server settings (dsn, redis, bind, auth)."
        )
    return server_config, unified.profile, unified.risk_hub


def create_app(
    *,
    bus: ControlBusProducer | None = None,
    bus_consumer: RiskHubControlBusConsumer | None = None,
    risk_hub_token: str | None = None,
    storage: Storage | None = None,
    storage_factory: Callable[[], Awaitable[Storage | StorageHandle]] | None = None,
    config: WorldServiceServerConfig | None = None,
    config_path: str | Path | None = None,
    rebalance_executor: Any | None = None,
    compat_rebalance_v2: bool | None = None,
    alpha_metrics_required: bool | None = None,
    extended_validation_scheduler: Callable[[Awaitable[int]], Any] | None = None,
    profile: DeploymentProfile | str | None = None,
    risk_hub: RiskSignalHub | None = None,
    risk_hub_config: RiskHubConfig | None = None,
) -> FastAPI:
    if storage is not None and storage_factory is not None:
        raise ValueError("Provide either storage or storage_factory, not both")

    resolved_config: WorldServiceServerConfig | None = config
    resolved_risk_hub_config: RiskHubConfig | None = risk_hub_config
    resolved_profile = _coerce_profile(profile)
    factory: Callable[[], Awaitable[Storage | StorageHandle]] | None = storage_factory

    should_load_config = (
        resolved_config is None
        and (
            config_path is not None
            or (storage is None and factory is None)
        )
    )
    if should_load_config:
        resolved_config, config_profile, resolved_risk_hub_config = _load_server_config(
            config, config_path=config_path
        )
        if resolved_profile is None:
            resolved_profile = config_profile
    if resolved_config is not None and storage is None and factory is None:
        if resolved_config.redis:
            factory = _config_storage_factory(resolved_config)
        elif resolved_profile is DeploymentProfile.PROD:
            raise RuntimeError(
                "Prod profile requires worldservice.server.redis for activation cache"
            )
        else:
            logger.warning(
                "WorldService Redis not configured; using in-memory storage (dev profile)"
            )

    if resolved_profile is None:
        resolved_profile = DeploymentProfile.DEV

    store = storage or Storage()
    if storage is not None:
        _enforce_persistent_storage(storage, profile=resolved_profile)

    if resolved_profile is DeploymentProfile.PROD and storage is None and factory is None:
        raise RuntimeError(
            "Prod profile requires PersistentStorage; supply storage or redis/dsn config"
        )

    if factory is not None and resolved_profile is DeploymentProfile.PROD:
        original_factory = factory

        async def _guarded_factory() -> StorageHandle:
            handle = _coerce_storage_handle(await original_factory())
            _enforce_persistent_storage(handle, profile=resolved_profile)
            return handle

        factory = _guarded_factory
    inline_cov_threshold = _resolve_inline_threshold(resolved_risk_hub_config)
    cache_ttl_override = (
        resolved_risk_hub_config.blob_store.cache_ttl
        if resolved_risk_hub_config is not None
        else None
    )
    blob_store = _build_hub_blob_store(
        resolved_risk_hub_config,
        redis_url=resolved_config.redis if resolved_config else None,
        profile=resolved_profile,
    )
    risk_hub_token = risk_hub_token or (
        resolved_risk_hub_config.token if resolved_risk_hub_config else None
    )

    if risk_hub is None:
        risk_hub = RiskSignalHub(
            cache=None,
            blob_store=blob_store,
            inline_cov_threshold=inline_cov_threshold
            if inline_cov_threshold is not None
            else 100,
        )
    elif blob_store is not None:
        risk_hub.bind_blob_store(blob_store)

    bus_instance: ControlBusProducer | None = bus
    if bus_instance is None and resolved_config is not None:
        brokers = resolved_config.controlbus_brokers
        topic = resolved_config.controlbus_topic
        if brokers and topic:
            bus_instance = ControlBusProducer(
                brokers=brokers,
                topic=topic,
                required=resolved_profile is DeploymentProfile.PROD,
                logger=logger,
            )
        elif resolved_profile is DeploymentProfile.PROD:
            raise RuntimeError(
                "Prod profile requires ControlBus brokers/topics for WorldService."
            )
        else:
            logger.warning(
                "ControlBus disabled for WorldService (dev profile): brokers/topics not configured"
            )

    if (
        bus_instance is None
        and resolved_profile is DeploymentProfile.PROD
        and resolved_config is None
    ):
        raise RuntimeError("Prod profile requires a ControlBus producer for WorldService.")

    if (
        resolved_profile is DeploymentProfile.PROD
        and isinstance(bus_instance, ControlBusProducer)
    ):
        bus_instance._required = True

    _bind_risk_hub_backend(risk_hub, store, cache_ttl=cache_ttl_override)
    service = WorldService(
        store=store,
        bus=bus_instance,
        rebalance_executor=rebalance_executor,
        extended_validation_scheduler=extended_validation_scheduler,
        risk_hub=risk_hub,
    )
    storage_handle: StorageHandle | None = None
    compat_flag = compat_rebalance_v2
    alpha_flag = alpha_metrics_required
    bus_consumer_instance = bus_consumer

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        nonlocal storage_handle, resolved_config, bus_instance, bus_consumer_instance
        try:
            if bus_instance is not None:
                try:
                    await bus_instance.start()
                except Exception:
                    if resolved_profile is DeploymentProfile.PROD:
                        raise
                    logger.warning(
                        "ControlBus disabled for WorldService (dev profile): startup failed",
                        exc_info=True,
                    )
                    service.bus = None
                    bus_instance = None
            if resolved_config and bus_consumer_instance is None:
                brokers = resolved_config.controlbus_brokers
                topic = resolved_config.controlbus_topic
                if brokers and topic:
                    bus_consumer_instance = RiskHubControlBusConsumer(
                        hub=risk_hub,
                        on_snapshot=lambda snap: service._apply_extended_validation(  # type: ignore[attr-defined]
                            world_id=snap.world_id,
                            stage=None,
                            policy_payload=None,
                        ),
                        dedupe_cache=getattr(risk_hub, "_cache", None),
                        brokers=brokers,
                        topic=topic,
                    )
            if bus_consumer_instance is not None:
                try:
                    await bus_consumer_instance.start()
                except Exception:
                    logger.exception("Failed to start risk hub consumer")
            if factory is not None:
                storage_handle = _coerce_storage_handle(await factory())
                service.store = storage_handle.storage
                _bind_risk_hub_backend(
                    risk_hub,
                    storage_handle.storage,
                    cache_ttl=cache_ttl_override,
                )
                app.state.storage = storage_handle.storage
            yield
        finally:
            if bus_consumer_instance is not None:
                with contextlib.suppress(Exception):  # pragma: no cover - defensive shutdown
                    await bus_consumer_instance.stop()
            if bus_instance is not None:
                try:
                    await bus_instance.stop()
                except Exception:  # pragma: no cover - defensive cleanup
                    logger.exception("Failed to stop ControlBus producer")
            target = storage_handle.storage if storage_handle else store
            shutdown = storage_handle.shutdown if storage_handle else None
            if shutdown is not None:
                try:
                    await shutdown()
                except Exception:  # pragma: no cover - defensive cleanup
                    logger.exception("Failed to shut down WorldService storage")
            else:
                close = getattr(target, "close", None)
                if close is not None:
                    try:
                        await _maybe_await(close())
                    except Exception:  # pragma: no cover - defensive cleanup
                        logger.exception("Failed to close WorldService storage")
            if rebalance_executor is not None:
                closer = getattr(rebalance_executor, "aclose", None) or getattr(
                    rebalance_executor, "close", None
                )
                if closer is not None:
                    try:
                        await _maybe_await(closer())
                    except Exception:  # pragma: no cover - defensive cleanup
                        logger.exception("Failed to close WorldService rebalance executor")

    if resolved_config is not None:
        if compat_flag is None:
            compat_flag = resolved_config.compat_rebalance_v2
        if alpha_flag is None:
            alpha_flag = resolved_config.alpha_metrics_required
    compat_flag = bool(compat_flag)
    alpha_flag = bool(alpha_flag)

    app = FastAPI(lifespan=lifespan)
    app.state.apply_locks = service.apply_locks
    app.state.apply_runs = service.apply_runs
    app.state.storage = store
    app.state.world_service = service
    app.state.worldservice_config = resolved_config
    app.state.risk_hub_consumer = bus_consumer
    app.state.rebalance_capabilities = {
        "compat_rebalance_v2": compat_flag,
        "alpha_metrics_required": alpha_flag,
    }
    app.include_router(create_worlds_router(service))
    app.include_router(create_policies_router(service))
    app.include_router(create_bindings_router(service))
    app.include_router(create_activation_router(service))
    app.include_router(create_allocations_router(service))
    app.include_router(create_evaluation_runs_router(service))
    app.include_router(create_live_monitoring_router(service))
    app.include_router(create_observability_router())
    app.include_router(
        create_risk_hub_router(
            risk_hub,
            bus=bus_instance,
            expected_token=risk_hub_token,
            schedule_extended_validation=lambda world_id: service._apply_extended_validation(  # type: ignore[attr-defined]
                world_id=world_id,
                stage=None,
                policy_payload=None,
            ),
        )
    )
    app.include_router(
        create_rebalancing_router(
            service,
            compat_rebalance_v2=compat_flag,
            alpha_metrics_required=alpha_flag,
        )
    )
    app.include_router(create_validations_router(service))
    return app


__all__ = [
    'World',
    'PolicyRequest',
    'ApplyPlan',
    'EvaluateRequest',
    'ApplyRequest',
    'ApplyResponse',
    'ApplyAck',
    'StorageHandle',
    'create_app',
]
