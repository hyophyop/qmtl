from __future__ import annotations

from typing import Optional

import redis.asyncio as redis


class RedisFIFOQueue:
    """Simple FIFO queue backed by Redis."""

    def __init__(self, redis_client: redis.Redis, name: str = "strategy_queue") -> None:
        self.redis = redis_client
        self.name = name

    async def push(self, item: str) -> None:
        """Append ``item`` to the queue."""
        await self.redis.rpush(self.name, item)

    async def pop(self) -> Optional[str]:
        """Pop the next item from the queue or ``None`` if empty."""
        data = await self.redis.lpop(self.name)
        if data is None:
            return None
        return data.decode() if isinstance(data, bytes) else data


__all__ = ["RedisFIFOQueue"]
