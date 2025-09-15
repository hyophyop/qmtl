from __future__ import annotations

from typing import Any, Awaitable, Callable, Optional

import logging
import redis.asyncio as redis


class RedisTaskQueue:
    """Simple FIFO task queue backed by Redis."""

    def __init__(self, redis_client: redis.Redis, name: str = "strategy_queue") -> None:
        self.redis = redis_client
        self.name = name

    async def _safe_redis_call(
        self, op: Callable[..., Awaitable[Any]], *args: Any
    ) -> Any | None:
        try:
            return await op(*args)
        except Exception as e:  # pragma: no cover - logging
            operation_name = getattr(op, "__name__", op.__class__.__name__)
            logging.error("Redis queue %s %s failed: %s", self.name, operation_name, e)
            return None

    async def push(self, item: str) -> bool:
        """Append ``item`` to the queue.

        Returns ``True`` on success, ``False`` otherwise.
        """
        result = await self._safe_redis_call(self.redis.rpush, self.name, item)
        return result is not None

    async def pop(self) -> Optional[str]:
        """Pop the next item from the queue or ``None`` if empty or on error."""
        data = await self._safe_redis_call(self.redis.lpop, self.name)
        if data is None:
            return None
        return data.decode() if isinstance(data, bytes) else data

    async def healthy(self) -> bool:
        """Return ``True`` if the underlying Redis connection is alive."""
        try:
            pong = await self.redis.ping()
            return bool(pong)
        except Exception:
            return False


__all__ = ["RedisTaskQueue"]
