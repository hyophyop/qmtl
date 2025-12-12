from __future__ import annotations

from typing import Iterable, Protocol, runtime_checkable


@runtime_checkable
class KafkaProducerLike(Protocol):
    async def start(self) -> None:  # pragma: no cover - interface
        ...

    async def stop(self) -> None:  # pragma: no cover - interface
        ...

    async def send_and_wait(self, topic: str, value: bytes, *, key: bytes | None = None) -> object:  # pragma: no cover - interface
        ...


@runtime_checkable
class KafkaConsumerLike(Protocol):
    async def start(self) -> None:  # pragma: no cover - interface
        ...

    async def stop(self) -> None:  # pragma: no cover - interface
        ...

    async def subscribe(self, topics: Iterable[str]) -> None:  # pragma: no cover - interface
        ...

    def __aiter__(self):  # pragma: no cover - interface
        ...


def create_kafka_producer(brokers: Iterable[str]) -> KafkaProducerLike | None:
    """Create an ``AIOKafkaProducer`` when available.

    Returns ``None`` if the optional ``aiokafka`` dependency is not installed or
    fails to import.
    """

    try:  # pragma: no cover - optional dependency
        from aiokafka import AIOKafkaProducer
    except Exception:
        return None
    return AIOKafkaProducer(bootstrap_servers=list(brokers))


def create_kafka_consumer(
    brokers: Iterable[str],
    *,
    group_id: str,
    auto_offset_reset: str = "latest",
    enable_auto_commit: bool = True,
) -> KafkaConsumerLike | None:
    """Create an ``AIOKafkaConsumer`` when available."""

    try:  # pragma: no cover - optional dependency
        from aiokafka import AIOKafkaConsumer
    except Exception:
        return None
    return AIOKafkaConsumer(
        bootstrap_servers=list(brokers),
        group_id=group_id,
        auto_offset_reset=auto_offset_reset,
        enable_auto_commit=bool(enable_auto_commit),
    )


__all__ = ["KafkaProducerLike", "KafkaConsumerLike", "create_kafka_producer", "create_kafka_consumer"]
