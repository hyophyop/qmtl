"""Order book imbalance transformation node."""

from qmtl.runtime.sdk.node import Node
from qmtl.runtime.sdk.cache_view import CacheView


def order_book_imbalance_node(
    bid_volume: Node,
    ask_volume: Node,
    *,
    interval: int | None = None,
    name: str | None = None,
) -> Node:
    """Return a node computing order book imbalance.

    The imbalance is ``(bid_volume - ask_volume) / (bid_volume + ask_volume)``.
    """

    interval = interval or bid_volume.interval

    def compute(view: CacheView):
        bid_data = view[bid_volume][interval]
        ask_data = view[ask_volume][interval]
        if not bid_data or not ask_data:
            return None
        b = bid_data[-1][1]
        a = ask_data[-1][1]
        total = b + a
        if total == 0:
            return None
        return (b - a) / total

    return Node(
        input=[bid_volume, ask_volume],
        compute_fn=compute,
        name=name or "order_book_imbalance",
        interval=interval,
    )


def order_book_imbalance(bid_volume: float, ask_volume: float) -> float:
    """Return order book imbalance from raw volumes."""
    total = bid_volume + ask_volume
    if total == 0:
        return 0.0
    return (bid_volume - ask_volume) / total


__all__ = ["order_book_imbalance_node", "order_book_imbalance"]
