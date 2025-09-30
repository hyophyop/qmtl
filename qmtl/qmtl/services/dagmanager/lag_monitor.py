from __future__ import annotations

"""Background task recording Kafka consumer lag per topic."""

from dataclasses import dataclass, field
from typing import Iterable, Protocol, Dict, Optional
import asyncio

from .kafka_admin import KafkaAdmin
from . import metrics


@dataclass(frozen=True)
class QueueLagInfo:
    topic: str
    committed_offset: int
    lag_alert_threshold: int


class LagStore(Protocol):
    """Provides queue lag metadata from Neo4j."""

    def list_queues(self) -> Iterable[QueueLagInfo]:
        ...


@dataclass
class LagMonitor:
    admin: KafkaAdmin
    store: LagStore

    def record_lag(self) -> Dict[str, int]:
        """Fetch lag for all queues and update metrics."""
        infos = list(self.store.list_queues())
        committed = {i.topic: i.committed_offset for i in infos}
        lags = self.admin.topic_lag(committed)
        for info in infos:
            lag = lags.get(info.topic, 0)
            metrics.observe_queue_lag(info.topic, lag, info.lag_alert_threshold)
        return lags


@dataclass
class LagMonitorLoop:
    monitor: LagMonitor
    interval: float = 30.0
    _task: Optional[asyncio.Task] = None
    _stop_event: asyncio.Event = field(
        default_factory=asyncio.Event, init=False, repr=False
    )

    async def start(self) -> None:
        if self._task is None:
            self._stop_event.clear()
            self._task = asyncio.create_task(self._run())

    async def _run(self) -> None:
        try:
            while not self._stop_event.is_set():
                self.monitor.record_lag()
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(), timeout=self.interval
                    )
                except asyncio.TimeoutError:
                    pass
        except asyncio.CancelledError:  # pragma: no cover - background task
            pass

    async def stop(self) -> None:
        if self._task is not None:
            self._stop_event.set()
            try:
                await self._task
            finally:
                self._task = None
                self._stop_event = asyncio.Event()


__all__ = ["LagMonitor", "LagMonitorLoop", "QueueLagInfo", "LagStore"]
