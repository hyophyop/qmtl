from __future__ import annotations

"""Simple Kafka Admin wrapper for idempotent topic creation."""

from dataclasses import dataclass
from typing import Protocol, Mapping

from .topic import TopicConfig


class AdminClient(Protocol):
    """Protocol describing minimal Kafka admin client methods."""

    def list_topics(self) -> Mapping[str, dict]:
        ...

    def create_topic(
        self,
        name: str,
        *,
        num_partitions: int,
        replication_factor: int,
        config: Mapping[str, str] | None = None,
    ) -> None:
        ...


@dataclass
class KafkaAdmin:
    client: AdminClient

    def create_topic_if_needed(self, name: str, config: TopicConfig) -> None:
        """Create topic if it does not exist."""
        topics = self.client.list_topics()
        if name in topics:
            return
        self.client.create_topic(
            name,
            num_partitions=config.partitions,
            replication_factor=config.replication_factor,
            config={"retention.ms": str(config.retention_ms)},
        )


__all__ = ["KafkaAdmin", "AdminClient"]
