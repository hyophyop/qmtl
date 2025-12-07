from __future__ import annotations

import inspect
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, cast

import redis.asyncio as redis
from fastapi import FastAPI

from qmtl.foundation.config import DeploymentProfile, find_config_file, load_config

from .controlbus_producer import ControlBusProducer
from .config import WorldServiceServerConfig
from .routers import (
    create_activation_router,
    create_allocations_router,
    create_bindings_router,
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


def _coerce_profile(value: DeploymentProfile | str | None) -> DeploymentProfile | None:
    if value is None:
        return None
    if isinstance(value, DeploymentProfile):
        return value
    return DeploymentProfile(value.lower())


def _load_server_config(
    config: WorldServiceServerConfig | None,
    *,
    config_path: str | Path | None = None,
) -> tuple[WorldServiceServerConfig, DeploymentProfile]:
    if config is not None:
        return config, DeploymentProfile.DEV

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
    return server_config, unified.profile


def create_app(
    *,
    bus: ControlBusProducer | None = None,
    storage: Storage | None = None,
    storage_factory: Callable[[], Awaitable[Storage | StorageHandle]] | None = None,
    config: WorldServiceServerConfig | None = None,
    config_path: str | Path | None = None,
    rebalance_executor: Any | None = None,
    compat_rebalance_v2: bool | None = None,
    alpha_metrics_required: bool | None = None,
    profile: DeploymentProfile | str | None = None,
) -> FastAPI:
    if storage is not None and storage_factory is not None:
        raise ValueError("Provide either storage or storage_factory, not both")

    resolved_config: WorldServiceServerConfig | None = config
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
        resolved_config, config_profile = _load_server_config(
            config, config_path=config_path
        )
        if resolved_profile is None:
            resolved_profile = config_profile
    if resolved_config is not None and storage is None and factory is None:
        if resolved_config.redis:
            factory = _config_storage_factory(resolved_config)

    if resolved_profile is None:
        resolved_profile = DeploymentProfile.DEV

    store = storage or Storage()
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

    service = WorldService(
        store=store, bus=bus_instance, rebalance_executor=rebalance_executor
    )
    storage_handle: StorageHandle | None = None
    compat_flag = compat_rebalance_v2
    alpha_flag = alpha_metrics_required

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        nonlocal storage_handle, resolved_config, bus_instance
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
            if factory is not None:
                storage_handle = _coerce_storage_handle(await factory())
                service.store = storage_handle.storage
                app.state.storage = storage_handle.storage
            yield
        finally:
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
    app.state.rebalance_capabilities = {
        "compat_rebalance_v2": compat_flag,
        "alpha_metrics_required": alpha_flag,
    }
    app.include_router(create_worlds_router(service))
    app.include_router(create_policies_router(service))
    app.include_router(create_bindings_router(service))
    app.include_router(create_activation_router(service))
    app.include_router(create_allocations_router(service))
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
