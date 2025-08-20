"""Order book imbalance transformation node."""

from qmtl.sdk.node import Node
from .utils import normalized_difference, create_imbalance_node


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
    return create_imbalance_node(
        bid_volume,
        ask_volume,
        interval=interval,
        name=name or "order_book_imbalance",
    )


def order_book_imbalance(bid_volume: float, ask_volume: float) -> float:
    """Return order book imbalance from raw volumes."""
    result = normalized_difference(bid_volume, ask_volume)
    return result if result is not None else 0.0


__all__ = ["order_book_imbalance_node", "order_book_imbalance"]
