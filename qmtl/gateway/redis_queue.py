from __future__ import annotations

from typing import Optional

import logging
import redis.asyncio as redis


class RedisTaskQueue:
    """Simple FIFO task queue backed by Redis."""

    def __init__(self, redis_client: redis.Redis, name: str = "strategy_queue") -> None:
        self.redis = redis_client
        self.name = name

    async def push(self, item: str) -> bool:
        """Append ``item`` to the queue.

        Returns ``True`` on success, ``False`` otherwise.
        """
        try:
            await self.redis.rpush(self.name, item)
            return True
        except Exception as e:  # pragma: no cover - logging
            logging.error("Redis queue %s push failed: %s", self.name, e)
            return False

    async def pop(self) -> Optional[str]:
        """Pop the next item from the queue or ``None`` if empty or on error."""
        try:
            data = await self.redis.lpop(self.name)
        except Exception as e:  # pragma: no cover - logging
            logging.error("Redis queue %s pop failed: %s", self.name, e)
            return None
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
