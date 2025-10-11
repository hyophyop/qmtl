from __future__ import annotations

import inspect
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

import redis.asyncio as redis
from fastapi import FastAPI

from qmtl.foundation.config import find_config_file, load_config

from .controlbus_producer import ControlBusProducer
from .config import WorldServiceServerConfig
from .routers import (
    create_activation_router,
    create_bindings_router,
    create_policies_router,
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
        storage = await PersistentStorage.create(db_dsn=config.dsn, redis_client=redis_client)

        async def _shutdown() -> None:
            await storage.close()
            try:
                if hasattr(redis_client, "aclose"):
                    await _maybe_await(redis_client.aclose())
                elif hasattr(redis_client, "close"):
                    await _maybe_await(redis_client.close())
            except Exception:  # pragma: no cover - defensive cleanup
                logger.exception("Failed to close WorldService Redis client")
            pool = getattr(redis_client, "connection_pool", None)
            if pool is not None and hasattr(pool, "disconnect"):
                await _maybe_await(pool.disconnect())  # type: ignore[misc]

        return StorageHandle(storage=storage, shutdown=_shutdown)

    return _factory


def _load_server_config(config: WorldServiceServerConfig | None) -> WorldServiceServerConfig:
    if config is not None:
        return config

    config_path = find_config_file()
    if config_path is None:
        raise RuntimeError(
            "WorldService configuration file not found. Set QMTL_CONFIG_FILE or create qmtl.yml in the working directory."
        )

    unified = load_config(config_path)
    server_config = unified.worldservice.server
    if server_config is None:
        raise RuntimeError(
            "WorldService configuration missing 'worldservice' server settings (dsn, redis, bind, auth)."
        )
    return server_config


def create_app(
    *,
    bus: ControlBusProducer | None = None,
    storage: Storage | None = None,
    storage_factory: Callable[[], Awaitable[Storage | StorageHandle]] | None = None,
    config: WorldServiceServerConfig | None = None,
) -> FastAPI:
    if storage is not None and storage_factory is not None:
        raise ValueError("Provide either storage or storage_factory, not both")

    resolved_config: WorldServiceServerConfig | None = None
    factory: Callable[[], Awaitable[Storage | StorageHandle]] | None = storage_factory
    if storage is None and factory is None:
        resolved_config = _load_server_config(config)
        factory = _config_storage_factory(resolved_config)

    store = storage or Storage()
    service = WorldService(store=store, bus=bus)
    storage_handle: StorageHandle | None = None

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        nonlocal storage_handle, resolved_config
        try:
            if factory is not None:
                storage_handle = _coerce_storage_handle(await factory())
                service.store = storage_handle.storage
                app.state.storage = storage_handle.storage
            yield
        finally:
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

    app = FastAPI(lifespan=lifespan)
    app.state.apply_locks = service.apply_locks
    app.state.apply_runs = service.apply_runs
    app.state.storage = store
    app.state.world_service = service
    app.state.worldservice_config = resolved_config
    app.include_router(create_worlds_router(service))
    app.include_router(create_policies_router(service))
    app.include_router(create_bindings_router(service))
    app.include_router(create_activation_router(service))
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
