from __future__ import annotations

from typing import Any, Awaitable, Callable, Optional

import logging
import redis.asyncio as redis


class RedisTaskQueue:
    """Simple FIFO task queue backed by Redis."""

    DEFAULT_LOCK_TTL_MS = 60_000

    def __init__(
        self,
        redis_client: redis.Redis,
        name: str = "strategy_queue",
        lock_ttl_ms: int = DEFAULT_LOCK_TTL_MS,
    ) -> None:
        self.redis = redis_client
        self.name = name
        self._lock_ttl_ms = lock_ttl_ms

    async def _safe_redis_call(
        self, op: Callable[..., Awaitable[Any]], *args: Any, **kwargs: Any
    ) -> Any | None:
        try:
            return await op(*args, **kwargs)
        except Exception as e:  # pragma: no cover - logging
            operation_name = getattr(op, "__name__", op.__class__.__name__)
            logging.error("Redis queue %s %s failed: %s", self.name, operation_name, e)
            return None

    @staticmethod
    def _decode(value: Any) -> Any:
        if isinstance(value, bytes):
            return value.decode()
        return value

    def _lock_key(self, item: str) -> str:
        return f"lock:{item}"

    async def push(self, item: str) -> bool:
        """Append ``item`` to the queue.

        Returns ``True`` on success, ``False`` otherwise.
        """
        result = await self._safe_redis_call(self.redis.rpush, self.name, item)
        return result is not None

    async def pop(self, owner: str, lock_ttl_ms: Optional[int] = None) -> Optional[str]:
        """Pop the next item from the queue or ``None`` if empty or on error.

        The caller must provide ``owner`` so a Redis ``SETNX`` lock can be acquired
        before removing the entry. When a lock already exists the queue head is
        left untouched and ``None`` is returned.
        """

        ttl_ms = lock_ttl_ms or self._lock_ttl_ms
        head = await self._safe_redis_call(self.redis.lindex, self.name, 0)
        if head is None:
            return None

        item = self._decode(head)
        lock_key = self._lock_key(str(item))

        locked = await self._safe_redis_call(
            self.redis.set,
            lock_key,
            owner,
            nx=True,
            px=ttl_ms,
        )

        if not locked:
            return None

        data = await self._safe_redis_call(self.redis.lpop, self.name)
        if data is None:
            await self.release(str(item), owner)
            return None

        value = self._decode(data)
        if value != item:
            await self.release(str(item), owner)
            return None

        return str(value)

    async def release(self, item: str, owner: str) -> None:
        """Release the Redis lock for ``item`` if held by ``owner``."""

        lock_key = self._lock_key(item)
        current_owner = await self._safe_redis_call(self.redis.get, lock_key)
        if current_owner is None:
            return

        current_owner = self._decode(current_owner)
        if current_owner != owner:
            return

        await self._safe_redis_call(self.redis.delete, lock_key)

    async def healthy(self) -> bool:
        """Return ``True`` if the underlying Redis connection is alive."""
        try:
            pong = await self.redis.ping()
            return bool(pong)
        except Exception:
            return False


__all__ = ["RedisTaskQueue"]
