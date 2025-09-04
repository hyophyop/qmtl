from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Optional

from .garbage_collector import GarbageCollector


@dataclass
class GCScheduler:
    """Run :meth:`GarbageCollector.collect` periodically."""

    gc: GarbageCollector
    interval: float = 60.0
    _task: Optional[asyncio.Task] = None
    _stop_event: asyncio.Event = field(
        default_factory=asyncio.Event, init=False, repr=False
    )

    async def start(self) -> None:
        """Begin scheduling in the background."""
        if self._task is None:
            self._stop_event.clear()
            self._task = asyncio.create_task(self._run())

    async def _run(self) -> None:
        try:
            while not self._stop_event.is_set():
                self.gc.collect()
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(), timeout=self.interval
                    )
                except asyncio.TimeoutError:
                    pass
        except asyncio.CancelledError:  # pragma: no cover - background task
            pass

    async def stop(self) -> None:
        """Stop the scheduler."""
        if self._task is not None:
            self._stop_event.set()
            try:
                await self._task
            finally:
                self._task = None
                self._stop_event = asyncio.Event()


__all__ = ["GCScheduler"]
