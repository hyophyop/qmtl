"""Publish trade signals to Kafka without modifying payload."""

from __future__ import annotations

from typing import Any

from qmtl.runtime.sdk.node import Node
from qmtl.runtime.sdk.cache_view import CacheView
from qmtl.runtime.sdk import metrics as sdk_metrics


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
    """Convert trade signals into standardized order payloads.

    Forwarded fields (when present):
    - action → side (BUY/SELL)
    - size → quantity
    - symbol
    - type (e.g., market/limit)
    - limit_price (or price → limit_price)
    - stop_loss, take_profit
    - client_order_id (or newClientOrderId → client_order_id)
    """

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
        # Optional fields for richer connectors
        if "symbol" in signal:
            order["symbol"] = signal["symbol"]
        if "type" in signal:
            order["type"] = signal["type"]
        if "limit_price" in signal:
            order["limit_price"] = signal["limit_price"]
        elif "price" in signal:
            order["limit_price"] = signal["price"]
        if "stop_loss" in signal:
            order["stop_loss"] = signal["stop_loss"]
        if "take_profit" in signal:
            order["take_profit"] = signal["take_profit"]
        if "client_order_id" in signal:
            order["client_order_id"] = signal["client_order_id"]
        elif "newClientOrderId" in signal:
            order["client_order_id"] = signal["newClientOrderId"]
        try:
            sdk_metrics.record_order_published()
        except Exception:
            pass
        return order
