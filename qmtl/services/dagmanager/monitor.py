from __future__ import annotations

"""Monitoring and recovery actions for DAG Manager."""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Protocol, Optional
import asyncio

from .alerts import AlertManager


class MetricsBackend(Protocol):
    """Expose system metrics used to detect failures."""

    def neo4j_leader_is_null(self) -> bool:
        ...

    def kafka_zookeeper_disconnects(self) -> int:
        ...

    def queue_lag_seconds(self, topic: str) -> tuple[float, float]:
        """Return current lag and alert threshold for ``topic``."""

        ...

    def diff_duration_ms_p95(self) -> float:
        ...


class AckStatus(Enum):
    """Result of waiting for a chunk ACK from the client."""

    OK = auto()
    TIMEOUT = auto()


class Neo4jCluster(Protocol):
    """Control interface for Neo4j cluster."""

    def elect_leader(self) -> None:
        ...


class KafkaSession(Protocol):
    """Control interface for Kafka admin connection."""

    def retry(self) -> None:
        ...


class DiffStream(Protocol):
    """Interface to inspect and resume diff streams."""

    def ack_status(self) -> AckStatus:
        ...

    def resume_from_last_offset(self) -> None:
        ...


@dataclass
class Monitor:
    metrics: MetricsBackend
    neo4j: Neo4jCluster
    kafka: KafkaSession
    stream: DiffStream
    alerts: AlertManager
    lag_topics: list[str] = field(default_factory=list)
    diff_duration_threshold_ms: float = 200.0

    async def check_once(self) -> None:
        """Inspect metrics once and trigger recovery/alerts."""
        alerts = []

        if self.metrics.neo4j_leader_is_null():
            self.neo4j.elect_leader()
            alerts.append(self.alerts.send_pagerduty("Neo4j leader down"))

        if self.metrics.kafka_zookeeper_disconnects() > 0:
            self.kafka.retry()
            alerts.append(self.alerts.send_slack("Kafka session lost"))

        if self.stream.ack_status() is AckStatus.TIMEOUT:
            self.stream.resume_from_last_offset()
            alerts.append(self.alerts.send_slack("Diff stream stalled"))

        for topic in self.lag_topics:
            lag, threshold = self.metrics.queue_lag_seconds(topic)
            if lag > threshold:
                alerts.append(
                    self.alerts.send_slack("Queue lag high", topic=topic)
                )

        if self.metrics.diff_duration_ms_p95() > self.diff_duration_threshold_ms:
            alerts.append(self.alerts.send_slack("Diff duration high"))

        if alerts:
            await asyncio.gather(*alerts)


@dataclass
class MonitorLoop:
    """Periodically run :class:`Monitor.check_once` in the background."""

    monitor: Monitor
    interval: float = 5.0
    _task: Optional[asyncio.Task] = None
    _stop_event: asyncio.Event = field(
        default_factory=asyncio.Event, init=False, repr=False
    )

    async def start(self) -> None:
        """Begin the monitoring loop."""
        if self._task is None:
            self._stop_event.clear()
            self._task = asyncio.create_task(self._run())

    async def _run(self) -> None:
        try:
            while not self._stop_event.is_set():
                await self.monitor.check_once()
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(), timeout=self.interval
                    )
                except asyncio.TimeoutError:
                    pass
        except asyncio.CancelledError:  # pragma: no cover - background task
            pass

    async def stop(self) -> None:
        """Cancel the running loop."""
        if self._task is not None:
            self._stop_event.set()
            try:
                await self._task
            finally:
                self._task = None
                self._stop_event = asyncio.Event()


__all__ = [
    "Monitor",
    "MetricsBackend",
    "AckStatus",
    "Neo4jCluster",
    "KafkaSession",
    "DiffStream",
    "MonitorLoop",
]
