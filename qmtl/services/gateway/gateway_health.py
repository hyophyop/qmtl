from __future__ import annotations

import asyncio
import inspect
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional, TYPE_CHECKING

import redis.asyncio as redis

if TYPE_CHECKING:  # pragma: no cover - optional import for typing
    from .dagmanager_client import DagManagerClient
    from .database import Database
    from .world_client import WorldServiceClient


@dataclass(frozen=True, slots=True)
class GatewayHealthCapabilities:
    """Feature/capability bits surfaced via the health endpoint."""

    rebalance_schema_version: int = 1
    alpha_metrics_capable: bool = False
    compute_context_contract: str | None = None

    def as_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "rebalance_schema_version": self.rebalance_schema_version,
            "alpha_metrics_capable": self.alpha_metrics_capable,
        }
        if self.compute_context_contract:
            payload["compute_context_contract"] = self.compute_context_contract
        return payload

    @property
    def cache_key(self) -> tuple[int, bool, str | None]:
        return (
            self.rebalance_schema_version,
            self.alpha_metrics_capable,
            self.compute_context_contract,
        )


@dataclass(slots=True)
class GatewayHealthCollector:
    redis_client: Optional[redis.Redis]
    database: Optional["Database"]
    dag_client: Optional[DagManagerClient]
    world_client: Optional["WorldServiceClient"]
    capabilities: GatewayHealthCapabilities
    timeout: float

    async def collect(self) -> dict[str, Any]:
        redis_status, postgres_status, dag_status = await asyncio.gather(
            self._probe_redis(),
            self._probe_postgres(),
            self._probe_dagmanager(),
        )
        world_status = self._world_status()
        overall = self._derive_overall(
            redis_status, postgres_status, dag_status, world_status
        )
        result: dict[str, Any] = {
            "status": overall,
            "redis": redis_status,
            "postgres": postgres_status,
            "dagmanager": dag_status,
            "worldservice": world_status,
            "capabilities": self.capabilities.as_payload(),
            "rebalance_schema_version": self.capabilities.rebalance_schema_version,
            "alpha_metrics_capable": self.capabilities.alpha_metrics_capable,
        }
        return result

    async def _probe_redis(self) -> str:
        client = self.redis_client
        if client is None:
            return "unknown"

        async def _call() -> Any:
            result = client.ping()
            if inspect.isawaitable(result):
                result = await result
            return bool(result)

        return await self._probe(_call)

    async def _probe_postgres(self) -> str:
        db = self.database
        if db is None or not hasattr(db, "healthy"):
            return "unknown"

        async def _call() -> bool:
            result = await db.healthy()
            return bool(result)

        return await self._probe(_call)

    async def _probe_dagmanager(self) -> str:
        dag_client = self.dag_client
        if dag_client is None:
            return "unknown"

        async def _call() -> bool:
            return bool(await dag_client.status())

        return await self._probe(_call)

    async def _probe(self, func: Callable[[], Awaitable[Any]]) -> str:
        try:
            result = await asyncio.wait_for(func(), timeout=self.timeout)
        except asyncio.TimeoutError:
            return "timeout"
        except Exception:
            return "error"
        return "ok" if result else "error"

    def _world_status(self) -> str:
        if self.world_client is None or not hasattr(self.world_client, "breaker"):
            return "unknown"
        return "open" if self.world_client.breaker.is_open else "ok"

    @staticmethod
    def _derive_overall(
        redis_status: str, postgres_status: str, dag_status: str, world_status: str
    ) -> str:
        statuses = (redis_status, postgres_status, dag_status, world_status)
        return "ok" if all(status == "ok" for status in statuses) else "degraded"


_STATUS_CACHE_MAP: dict[tuple[int, int, int, int, tuple[int, bool, str | None], float], tuple[float, dict[str, Any]]] = {}
_STATUS_CACHE_TS: float = 0.0
_STATUS_CACHE_TTL = 2.0  # seconds
_STATUS_LOCK = asyncio.Lock()


def reset_status_cache() -> None:
    """Clear gateway health cache. Intended for tests."""

    _STATUS_CACHE_MAP.clear()
    global _STATUS_CACHE_TS
    _STATUS_CACHE_TS = 0.0


async def get_health(
    redis_client: Optional[redis.Redis] = None,
    database: Optional["Database"] = None,
    dag_client: Optional[DagManagerClient] = None,
    world_client: Optional["WorldServiceClient"] = None,
    *,
    capabilities: GatewayHealthCapabilities | None = None,
    timeout: float = 0.75,
) -> dict[str, Any]:
    """Return health information for gateway and dependencies.

    Results are cached for a short time to avoid spamming external
    dependencies with health checks when multiple requests arrive
    concurrently.
    """
    global _STATUS_CACHE_MAP, _STATUS_CACHE_TS

    now = time.monotonic()
    caps = capabilities or GatewayHealthCapabilities()
    key = (
        id(redis_client) if redis_client is not None else 0,
        id(database) if database is not None else 0,
        id(dag_client) if dag_client is not None else 0,
        id(world_client) if world_client is not None else 0,
        caps.cache_key,
        timeout,
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

        collector = GatewayHealthCollector(
            redis_client=redis_client,
            database=database,
            dag_client=dag_client,
            world_client=world_client,
            capabilities=caps,
            timeout=timeout,
        )
        result = await collector.collect()
        _STATUS_CACHE_MAP[key] = (now, result)
        _STATUS_CACHE_TS = now
        return result


__all__ = ["GatewayHealthCapabilities", "get_health", "reset_status_cache"]
