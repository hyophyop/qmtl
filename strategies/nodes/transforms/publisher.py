"""Publish trade signals to Kafka without modifying payload."""

from __future__ import annotations

from typing import Any, Tuple

from qmtl.sdk.node import Node
from qmtl.sdk.cache_view import CacheView


def publisher_node(signal: Any, *, topic: str) -> Tuple[str, Any]:
    """Return the given ``signal`` and ``topic`` pair.

    Parameters
    ----------
    signal:
        Message payload to publish.
    topic:
        Kafka topic name for the ``signal``.

    Returns
    -------
    tuple[str, Any]
        A ``(topic, signal)`` tuple that leaves ``signal`` untouched.
    """

    return topic, signal


class TradeOrderPublisherNode(Node):
    """Node wrapper that forwards trade orders for publishing."""

    def __init__(
        self,
        signal: Node,
        *,
        topic: str,
        name: str | None = None,
    ) -> None:
        self.signal = signal
        self.topic = topic
        super().__init__(
            input=signal,
            compute_fn=self._compute,
            name=name or f"{signal.name}_publisher",
            interval=signal.interval,
            period=1,
        )

    def _compute(self, view: CacheView) -> Any | None:
        data = view[self.signal][self.signal.interval]
        if not data:
            return None
        _, payload = data[-1]
        _, order = publisher_node(payload, topic=self.topic)
        return order
