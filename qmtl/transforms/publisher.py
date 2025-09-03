"""Publish trade signals to Kafka without modifying payload."""

from __future__ import annotations

from typing import Any

from qmtl.sdk.node import Node
from qmtl.sdk.cache_view import CacheView


def publisher_node(signal: Any) -> Any:
    """Return ``signal`` unchanged.

    The Runner's hooks determine the publication destination; this function
    simply forwards the payload without embedding any topic information.

    Parameters
    ----------
    signal:
        Message payload to publish.

    Returns
    -------
    Any
        The ``signal`` payload.
    """

    return signal


class TradeOrderPublisherNode(Node):
    """Convert trade signals into order payloads."""

    def __init__(
        self,
        signal: Node,
        *,
        name: str | None = None,
    ) -> None:
        self.signal = signal
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
