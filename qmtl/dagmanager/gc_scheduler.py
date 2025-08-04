from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Optional

from .gc import GarbageCollector


@dataclass
class GCScheduler:
    """Run :meth:`GarbageCollector.collect` periodically."""

    gc: GarbageCollector
    interval: float = 60.0
    _task: Optional[asyncio.Task] = None
    _queue: asyncio.Queue[asyncio.Future[object]] = field(
        default_factory=asyncio.Queue, init=False
    )

    async def start(self) -> None:
        """Begin scheduling in the background."""
        if self._task is None:
            self._task = asyncio.create_task(self._run())

    async def trigger(self) -> object:
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[object] = loop.create_future()
        await self._queue.put(fut)
        return await fut

    async def _run(self) -> None:
        try:
            while True:
                fut = await self._queue.get()
                try:
                    result = self.gc.collect()
                    fut.set_result(result)
                except Exception as exc:  # pragma: no cover - pass through
                    fut.set_exception(exc)
        except asyncio.CancelledError:  # pragma: no cover - background task
            pass

    async def stop(self) -> None:
        """Stop the scheduler."""
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            finally:
                self._task = None


__all__ = ["GCScheduler"]
