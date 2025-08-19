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
    """Convert trade signals into order payloads."""

    def __init__(
        self,
        signal: Node,
        *,
        topic: str,
        name: str | None = None,
    ) -> None:
        self.signal = signal
        # ``topic`` is kept for API compatibility though the Runner's hooks
        # ultimately decide the publication destination.
        self.topic = topic
        super().__init__(
            input=signal,
            compute_fn=self._compute,
            name=name or f"{signal.name}_publisher",
            interval=signal.interval,
            period=1,
        )

    def _compute(self, view: CacheView) -> dict | None:
        data = view[self.signal][self.signal.interval]
        if not data:
            return None
        ts, signal = data[-1]
        action = signal.get("action")
        if action not in {"BUY", "SELL"}:
            return None
        order: dict[str, Any] = {
            "side": action,
            "quantity": signal.get("size", 1.0),
            "timestamp": ts,
        }
        if "stop_loss" in signal:
            order["stop_loss"] = signal["stop_loss"]
        if "take_profit" in signal:
            order["take_profit"] = signal["take_profit"]
        return order
