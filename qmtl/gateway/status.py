from __future__ import annotations

from typing import Optional, TYPE_CHECKING

import redis.asyncio as redis

if TYPE_CHECKING:  # pragma: no cover - optional import for typing
    from .api import Database
from .dagmanager_client import DagManagerClient


async def get_status(
    redis_client: Optional[redis.Redis] = None,
    database: Optional[Database] = None,
    dag_client: Optional[DagManagerClient] = None,
) -> dict[str, str]:
    """Return status information for gateway and dependencies."""
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

    overall = (
        "ok" if redis_status == "ok" and postgres_status == "ok" and dag_status == "ok" else "degraded"
    )

    return {
        "status": overall,
        "redis": redis_status,
        "postgres": postgres_status,
        "dag_manager": dag_status,
    }

__all__ = ["get_status"]
