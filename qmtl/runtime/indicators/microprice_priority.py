"""Microprice and order-book imbalance indicators with priority weighting."""

from __future__ import annotations

from qmtl.runtime.sdk.cache_view import CacheView
from qmtl.runtime.sdk.node import Node

from .helpers import (
    best_order_book_level,
    extract_order_book_snapshot,
    sum_order_book_levels,
)

__all__ = ["microprice_imbalance"]


def _compute_microprice(
    bid_price: float | None,
    bid_size: float | None,
    ask_price: float | None,
    ask_size: float | None,
    epsilon: float,
) -> float | None:
    """Return the microprice using top-of-book price and size information."""

    if bid_price is None or ask_price is None:
        return None

    bid_depth = bid_size or 0.0
    ask_depth = ask_size or 0.0

    denominator = bid_depth + ask_depth + epsilon
    if denominator == 0.0:
        return 0.0

    numerator = ask_price * bid_depth + bid_price * ask_depth
    return numerator / denominator


def microprice_imbalance(
    source: Node,
    *,
    top_levels: int = 1,
    epsilon: float = 1e-9,
    name: str | None = None,
) -> Node:
    """Return a node computing microprice and depth imbalance metrics.

    Parameters
    ----------
    source:
        Node yielding order-book snapshots containing ``"bids"`` and
        ``"asks"`` sequences. Each level may be a ``(price, size)`` pair, a
        mapping with ``price``/``size`` keys, or a raw size value.
    top_levels:
        Number of levels from each side included in the imbalance sum.
    epsilon:
        Small constant added to denominators to avoid division by zero.
    name:
        Optional node name. Defaults to ``"microprice_imbalance"``.
    """

    def compute(view: CacheView) -> dict[str, float | None] | None:
        snapshot = extract_order_book_snapshot(view, source)
        if snapshot is None:
            return None

        bids = snapshot.get("bids")
        asks = snapshot.get("asks")

        bid_price, bid_size = best_order_book_level(bids)
        ask_price, ask_size = best_order_book_level(asks)

        microprice = _compute_microprice(bid_price, bid_size, ask_price, ask_size, epsilon)

        bid_total = sum_order_book_levels(bids, top_levels)
        ask_total = sum_order_book_levels(asks, top_levels)

        if bid_total == 0.0 and ask_total == 0.0:
            imbalance = 0.0
        else:
            denominator = bid_total + ask_total + epsilon
            imbalance = (bid_total - ask_total) / denominator

        return {
            "microprice": microprice,
            "imbalance": imbalance,
        }

    return Node(
        input=source,
        compute_fn=compute,
        name=name or "microprice_imbalance",
        interval=source.interval,
        period=source.period,
    )
