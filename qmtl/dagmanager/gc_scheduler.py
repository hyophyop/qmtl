from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Optional

from .gc import GarbageCollector


@dataclass
class GCScheduler:
    """Run :meth:`GarbageCollector.collect` periodically."""

    gc: GarbageCollector
    interval: float = 60.0
    _task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Begin scheduling in the background."""
        if self._task is None:
            self._task = asyncio.create_task(self._run())

    async def _run(self) -> None:
        try:
            while True:
                self.gc.collect()
                await asyncio.sleep(self.interval)
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
