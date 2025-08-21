"""Execution imbalance transform normalizing buy/sell volume difference."""

from qmtl.sdk.node import Node
from qmtl.sdk.cache_view import CacheView


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

    interval = interval or buy_volume.interval

    def compute(view: CacheView):
        buy_data = view[buy_volume][interval]
        sell_data = view[sell_volume][interval]
        if not buy_data or not sell_data:
            return None
        buy = buy_data[-1][1]
        sell = sell_data[-1][1]
        total = buy + sell
        if total == 0:
            return None
        return (buy - sell) / total

    return Node(
        input=(buy_volume, sell_volume),
        compute_fn=compute,
        name=name or "execution_imbalance",
        interval=interval,
        period=2,
    )


def execution_imbalance(buy: float, sell: float) -> float:
    """Return normalized execution imbalance."""
    total = buy + sell
    if total == 0:
        return 0.0
    return (buy - sell) / total


__all__ = ["execution_imbalance_node", "execution_imbalance"]
