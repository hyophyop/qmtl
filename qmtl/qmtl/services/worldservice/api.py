from __future__ import annotations

import inspect
import logging
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

import redis.asyncio as redis
from fastapi import FastAPI

from .controlbus_producer import ControlBusProducer
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


def _env_storage_factory() -> Callable[[], Awaitable[StorageHandle]] | None:
    db_dsn = os.getenv("QMTL_WORLDSERVICE_DB_DSN")
    redis_dsn = os.getenv("QMTL_WORLDSERVICE_REDIS_DSN")
    if not db_dsn or not redis_dsn:
        return None

    async def _factory() -> StorageHandle:
        redis_client = redis.from_url(redis_dsn, decode_responses=True)
        storage = await PersistentStorage.create(db_dsn=db_dsn, redis_client=redis_client)

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


def create_app(
    *,
    bus: ControlBusProducer | None = None,
    storage: Storage | None = None,
    storage_factory: Callable[[], Awaitable[Storage | StorageHandle]] | None = None,
) -> FastAPI:
    if storage is not None and storage_factory is not None:
        raise ValueError("Provide either storage or storage_factory, not both")

    factory = storage_factory or _env_storage_factory()
    store = storage or Storage()
    service = WorldService(store=store, bus=bus)
    storage_handle: StorageHandle | None = None

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        nonlocal storage_handle
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
