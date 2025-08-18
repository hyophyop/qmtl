from __future__ import annotations

"""Background tasks to record Neo4j graph counts."""

from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING
import asyncio

if TYPE_CHECKING:  # pragma: no cover - optional import for typing
    from neo4j import Driver

from . import metrics


@dataclass
class GraphCountCollector:
    """Fetch counts of core graph entities and publish metrics."""

    driver: "Driver"

    def record_counts(self) -> tuple[int, int]:
        """Query Neo4j for ``ComputeNode`` and ``Queue`` totals."""
        with self.driver.session() as session:
            compute = session.run(
                "MATCH (c:ComputeNode) RETURN count(c) AS c"
            ).single()["c"]
            queues = session.run(
                "MATCH (q:Queue) RETURN count(q) AS c"
            ).single()["c"]
        metrics.compute_nodes_total.set(compute)
        metrics.compute_nodes_total._val = compute  # type: ignore[attr-defined]
        metrics.queues_total.set(queues)
        metrics.queues_total._val = queues  # type: ignore[attr-defined]
        return compute, queues


@dataclass
class GraphCountScheduler:
    """Periodically update graph size metrics."""

    collector: GraphCountCollector
    interval: float = 60.0
    _task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run())

    async def _run(self) -> None:
        try:
            while True:
                self.collector.record_counts()
                await asyncio.sleep(self.interval)
        except asyncio.CancelledError:  # pragma: no cover - background task
            pass

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            finally:
                self._task = None


__all__ = ["GraphCountCollector", "GraphCountScheduler"]
