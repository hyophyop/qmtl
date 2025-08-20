"""Execution imbalance transform normalizing buy/sell volume difference."""

from qmtl.sdk.node import Node
from .utils import normalized_difference, create_imbalance_node


def execution_imbalance_node(
    buy_volume: Node,
    sell_volume: Node,
    *,
    interval: int | None = None,
    name: str | None = None,
) -> Node:
    """Return a node computing normalized execution imbalance.

    The imbalance is defined as ``(buy - sell) / (buy + sell)`` using the
    latest volumes from ``buy_volume`` and ``sell_volume`` nodes.
    """
    return create_imbalance_node(
        buy_volume,
        sell_volume,
        interval=interval,
        name=name or "execution_imbalance",
    )


def execution_imbalance(buy: float, sell: float) -> float:
    """Return normalized execution imbalance."""
    result = normalized_difference(buy, sell)
    return result if result is not None else 0.0


__all__ = ["execution_imbalance_node", "execution_imbalance"]
