from __future__ import annotations

"""Monitoring and recovery actions for DAG-Manager."""

from dataclasses import dataclass
from typing import Protocol, Optional
import asyncio

from .alerts import AlertManager


class MetricsBackend(Protocol):
    """Expose system metrics used to detect failures."""

    def neo4j_leader_is_null(self) -> bool:
        ...

    def kafka_zookeeper_disconnects(self) -> int:
        ...


class Neo4jCluster(Protocol):
    """Control interface for Neo4j cluster."""

    def elect_leader(self) -> None:
        ...


class KafkaSession(Protocol):
    """Control interface for Kafka admin connection."""

    def retry(self) -> None:
        ...


@dataclass
class Monitor:
    metrics: MetricsBackend
    neo4j: Neo4jCluster
    kafka: KafkaSession
    alerts: AlertManager

    async def check_once(self) -> None:
        """Inspect metrics once and trigger recovery/alerts."""
        if self.metrics.neo4j_leader_is_null():
            self.neo4j.elect_leader()
            await self.alerts.send_pagerduty("Neo4j leader down")

        if self.metrics.kafka_zookeeper_disconnects() > 0:
            self.kafka.retry()
            await self.alerts.send_slack("Kafka session lost")



@dataclass
class MonitorLoop:
    """Periodically run :class:`Monitor.check_once` in the background."""

    monitor: Monitor
    interval: float = 5.0
    _task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Begin the monitoring loop."""
        if self._task is None:
            self._task = asyncio.create_task(self._run())

    async def _run(self) -> None:
        try:
            while True:
                await self.monitor.check_once()
                await asyncio.sleep(self.interval)
        except asyncio.CancelledError:  # pragma: no cover - background task
            pass

    async def stop(self) -> None:
        """Cancel the running loop."""
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            finally:
                self._task = None


__all__ = [
    "Monitor",
    "MetricsBackend",
    "Neo4jCluster",
    "KafkaSession",
    "MonitorLoop",
]
