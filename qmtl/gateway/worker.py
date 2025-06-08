from __future__ import annotations

import asyncio
import uuid
from typing import Awaitable, Callable, Optional

import redis.asyncio as redis

from .api import Database
from .fsm import StrategyFSM
from .queue import RedisFIFOQueue


class StrategyWorker:
    """Async worker that processes strategies from a FIFO queue."""

    def __init__(
        self,
        redis_client: redis.Redis,
        database: Database,
        fsm: StrategyFSM,
        queue: RedisFIFOQueue,
        worker_id: Optional[str] = None,
        handler: Optional[Callable[[str], Awaitable[None]]] = None,
    ) -> None:
        self.redis = redis_client
        self.database = database
        self.fsm = fsm
        self.queue = queue
        self.worker_id = worker_id or str(uuid.uuid4())
        self._handler = handler

    async def _process(self, strategy_id: str) -> bool:
        lock_key = f"lock:{strategy_id}"
        locked = await self.redis.set(lock_key, self.worker_id, nx=True, px=60000)
        if not locked:
            return False
        try:
            await self.fsm.transition(strategy_id, "PROCESS")
            if self._handler:
                await self._handler(strategy_id)
            await self.fsm.transition(strategy_id, "COMPLETE")
            return True
        finally:
            # The lock expires automatically; explicit deletion would allow
            # another worker to reprocess the same strategy immediately.
            pass

    async def run_once(self) -> Optional[str]:
        """Pop and process a single strategy."""
        strategy_id = await self.queue.pop()
        if strategy_id is None:
            return None
        await self._process(strategy_id)
        return strategy_id


__all__ = ["StrategyWorker"]
