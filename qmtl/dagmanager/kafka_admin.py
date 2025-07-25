from __future__ import annotations

"""Simple Kafka Admin wrapper for idempotent topic creation."""

import asyncio
from dataclasses import dataclass, field
from typing import Protocol, Mapping, Dict

from qmtl.common import AsyncCircuitBreaker
from . import metrics

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


class InMemoryAdminClient:
    """Simple in-memory implementation of :class:`AdminClient`."""

    def __init__(self) -> None:
        self.topics: Dict[str, dict] = {}

    def list_topics(self) -> Mapping[str, dict]:
        return self.topics

    def create_topic(
        self,
        name: str,
        *,
        num_partitions: int,
        replication_factor: int,
        config: Mapping[str, str] | None = None,
    ) -> None:
        if name in self.topics:
            raise TopicExistsError
        self.topics[name] = {
            "config": dict(config or {}),
            "num_partitions": num_partitions,
            "replication_factor": replication_factor,
            "size": 0,
        }

    def get_size(self, name: str) -> int:
        return int(self.topics.get(name, {}).get("size", 0))


@dataclass
class KafkaAdmin:
    client: AdminClient
    breaker: AsyncCircuitBreaker = field(default_factory=AsyncCircuitBreaker)

    def __post_init__(self) -> None:
        """Attach metric callbacks without overriding existing hooks."""
        prev_on_open = self.breaker._on_open

        def _on_open() -> None:
            if prev_on_open is not None:
                prev_on_open()
            metrics.kafka_breaker_open_total.inc()

        self.breaker._on_open = _on_open

    def create_topic_if_needed(self, name: str, config: TopicConfig) -> None:
        """Create topic idempotently using a circuit breaker."""

        @self.breaker
        async def _create() -> None:
            try:
                self.client.create_topic(
                    name,
                    num_partitions=config.partitions,
                    replication_factor=config.replication_factor,
                    config={"retention.ms": str(config.retention_ms)},
                )
            except TopicExistsError:
                # Another admin may have created the topic concurrently.
                return

        # ``AsyncCircuitBreaker`` expects an async callable. ``asyncio.run``
        # executes the decorated coroutine in a fresh loop.
        asyncio.run(_create())

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


__all__ = [
    "KafkaAdmin",
    "AdminClient",
    "TopicExistsError",
    "InMemoryAdminClient",
]
