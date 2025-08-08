from __future__ import annotations

from typing import Any, Protocol


class Producer(Protocol):
    """Minimal Kafka producer interface used by :class:`Pipeline`."""

    def produce(self, topic: str, value: Any) -> None:  # pragma: no cover - interface
        ...

    def flush(self) -> None:  # pragma: no cover - interface
        ...


__all__ = ["Producer"]
