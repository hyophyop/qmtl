"""Publish trade signals to Kafka without modifying payload."""

from __future__ import annotations

from typing import Any, Callable

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
        _copy_if_present(signal, order, "symbol")
        _copy_if_present(signal, order, "type")
        _copy_first_of(signal, order, ("limit_price", "price"), target_key="limit_price")
        _copy_if_present(signal, order, "stop_loss")
        _copy_if_present(signal, order, "take_profit")
        _copy_first_of(
            signal,
            order,
            ("client_order_id", "newClientOrderId"),
            target_key="client_order_id",
        )
        try:
            sdk_metrics.record_order_published()
        except Exception:
            pass
        return order


def _copy_if_present(source: dict[str, Any], target: dict[str, Any], key: str) -> None:
    if key in source:
        target[key] = source[key]


def _copy_first_of(
    source: dict[str, Any], target: dict[str, Any], keys: tuple[str, ...], *, target_key: str
) -> None:
    for key in keys:
        if key in source:
            target[target_key] = source[key]
            return
