from __future__ import annotations

"""Monitoring and recovery actions for DAG-Manager."""

from dataclasses import dataclass
from typing import Protocol

from .alerts import AlertManager


class MetricsBackend(Protocol):
    """Expose system metrics used to detect failures."""

    def neo4j_leader_is_null(self) -> bool:
        ...

    def kafka_zookeeper_disconnects(self) -> int:
        ...

    def diff_chunk_ack_timeout(self) -> bool:
        ...


class Neo4jCluster(Protocol):
    """Control interface for Neo4j cluster."""

    def elect_leader(self) -> None:
        ...


class KafkaSession(Protocol):
    """Control interface for Kafka admin connection."""

    def retry(self) -> None:
        ...


class DiffStream(Protocol):
    """Interface to resume diff streams."""

    def resume_from_last_offset(self) -> None:
        ...


@dataclass
class Monitor:
    metrics: MetricsBackend
    neo4j: Neo4jCluster
    kafka: KafkaSession
    stream: DiffStream
    alerts: AlertManager

    def check_once(self) -> None:
        """Inspect metrics once and trigger recovery/alerts."""
        if self.metrics.neo4j_leader_is_null():
            self.neo4j.elect_leader()
            self.alerts.send_pagerduty("Neo4j leader down")

        if self.metrics.kafka_zookeeper_disconnects() > 0:
            self.kafka.retry()
            self.alerts.send_slack("Kafka session lost")

        if self.metrics.diff_chunk_ack_timeout():
            self.stream.resume_from_last_offset()
            self.alerts.send_slack("Diff stream stalled")


__all__ = ["Monitor", "MetricsBackend", "Neo4jCluster", "KafkaSession", "DiffStream"]
