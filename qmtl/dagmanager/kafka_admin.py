from __future__ import annotations

"""Simple Kafka Admin wrapper for idempotent topic creation."""

from dataclasses import dataclass
from typing import Protocol, Mapping, Dict

from .topic import TopicConfig


class TopicExistsError(Exception):
    """Raised when attempting to create a topic that already exists."""


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
        """Create topic idempotently."""
        try:
            self.client.create_topic(
                name,
                num_partitions=config.partitions,
                replication_factor=config.replication_factor,
                config={"retention.ms": str(config.retention_ms)},
            )
        except TopicExistsError:
            # another admin may have created the topic concurrently
            pass

    def get_topic_sizes(self) -> Dict[str, int]:
        """Return approximate message count per topic."""
        stats: Dict[str, int] = {}
        for name, meta in self.client.list_topics().items():
            size = meta.get("size")
            offsets = meta.get("offsets")
            if size is None and isinstance(offsets, Mapping):
                high = offsets.get("high", 0)
                low = offsets.get("low", 0)
                size = high - low
            if size is not None:
                stats[name] = int(size)
        return stats


__all__ = ["KafkaAdmin", "AdminClient", "TopicExistsError"]
