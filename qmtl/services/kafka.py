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


__all__ = ["KafkaProducerLike", "create_kafka_producer"]
