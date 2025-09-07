from __future__ import annotations

from typing import Optional, TYPE_CHECKING

import asyncio
import time

import redis.asyncio as redis

if TYPE_CHECKING:  # pragma: no cover - optional import for typing
    from .database import Database
    from .world_client import WorldServiceClient
from .dagmanager_client import DagManagerClient

_STATUS_CACHE_MAP: dict[tuple[int, int, int, int], tuple[float, dict[str, str]]] = {}
_STATUS_CACHE_TS: float = 0.0
_STATUS_CACHE_TTL = 2.0  # seconds
_STATUS_LOCK = asyncio.Lock()


async def get_health(
    redis_client: Optional[redis.Redis] = None,
    database: Optional[Database] = None,
    dag_client: Optional[DagManagerClient] = None,
    world_client: Optional[WorldServiceClient] = None,
) -> dict[str, str]:
    """Return health information for gateway and dependencies.

    Results are cached for a short time to avoid spamming external
    dependencies with health checks when multiple requests arrive
    concurrently.
    """
    global _STATUS_CACHE_MAP, _STATUS_CACHE_TS

    now = time.monotonic()
    key = (
        id(redis_client) if redis_client is not None else 0,
        id(database) if database is not None else 0,
        id(dag_client) if dag_client is not None else 0,
        id(world_client) if world_client is not None else 0,
    )
    cached = _STATUS_CACHE_MAP.get(key)
    if cached and now - cached[0] < _STATUS_CACHE_TTL:
        return cached[1]

    async with _STATUS_LOCK:
        # Re-check after acquiring the lock in case another coroutine
        # already refreshed the cache.
        now = time.monotonic()
        cached = _STATUS_CACHE_MAP.get(key)
        if cached and now - cached[0] < _STATUS_CACHE_TTL:
            return cached[1]

        redis_status = "unknown"
        if redis_client is not None:
            try:
                pong = await redis_client.ping()
                redis_status = "ok" if pong else "error"
            except Exception:
                redis_status = "error"

        postgres_status = "unknown"
        if database is not None and hasattr(database, "healthy"):
            try:
                postgres_status = "ok" if await database.healthy() else "error"
            except Exception:
                postgres_status = "error"

        dag_status = "unknown"
        if dag_client is not None:
            try:
                dag_status = "ok" if await dag_client.status() else "error"
            except Exception:
                dag_status = "error"

        world_status = "unknown"
        if world_client is not None:
            world_status = "open" if world_client.breaker.is_open else "ok"

        overall = (
            "ok"
            if redis_status == "ok"
            and postgres_status == "ok"
            and dag_status == "ok"
            and world_status == "ok"
            else "degraded"
        )

        result = {
            "status": overall,
            "redis": redis_status,
            "postgres": postgres_status,
            "dagmanager": dag_status,
            "worldservice": world_status,
        }
        _STATUS_CACHE_MAP[key] = (now, result)
        _STATUS_CACHE_TS = now
        return result

__all__ = ["get_health"]
