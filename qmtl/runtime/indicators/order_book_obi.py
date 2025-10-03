"""Order-book imbalance indicator nodes."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from qmtl.runtime.sdk.cache_view import CacheView
from qmtl.runtime.sdk.node import Node

from .ema import ema

__all__ = ["order_book_obi", "order_book_obi_ema"]


def _sum_levels(levels_data: Sequence[Any] | None, levels: int) -> float:
    """Return the summed depth over ``levels`` entries from ``levels_data``."""

    if not levels_data or levels <= 0:
        return 0.0

    total = 0.0
    taken = 0
    for level in levels_data:
        if taken >= levels:
            break
        if isinstance(level, (list, tuple)):
            if not level:
                continue
            raw_size = level[1] if len(level) > 1 else level[0]
        else:
            raw_size = level
        try:
            size = float(raw_size)
        except (TypeError, ValueError):
            continue
        total += size
        taken += 1
    return total


def order_book_obi(
    source: Node,
    *,
    levels: int = 1,
    epsilon: float = 1e-9,
    name: str | None = None,
) -> Node:
    """Return a node computing order-book imbalance from raw snapshots.

    Parameters
    ----------
    source:
        Node yielding order-book snapshots containing ``"bids"`` and
        ``"asks"`` sequences. Each level may be a ``(price, size)`` pair or a
        raw size value.
    levels:
        Number of levels from each side included in the imbalance sum.
    epsilon:
        Small constant added to the denominator to avoid division by zero.
    name:
        Optional node name. Defaults to ``"order_book_obi"``.
    """

    def compute(view: CacheView) -> float | None:
        series = view[source][source.interval]
        latest = series.latest()
        if latest is None:
            return None

        snapshot = latest[1]
        if snapshot is None or not isinstance(snapshot, Mapping):
            return None

        bids = snapshot.get("bids", [])
        asks = snapshot.get("asks", [])

        bid_total = _sum_levels(bids, levels)
        ask_total = _sum_levels(asks, levels)

        if bid_total == 0.0 and ask_total == 0.0:
            return 0.0

        denominator = bid_total + ask_total + epsilon
        return (bid_total - ask_total) / denominator

    return Node(
        input=source,
        compute_fn=compute,
        name=name or "order_book_obi",
        interval=source.interval,
        period=1,
    )


def order_book_obi_ema(
    source: Node,
    *,
    levels: int = 1,
    ema_period: int = 20,
    epsilon: float = 1e-9,
    name: str | None = None,
) -> Node:
    """Return an EMA-smoothed order-book imbalance node."""

    base_name = name or "order_book_obi_ema"
    obi_node = order_book_obi(
        source,
        levels=levels,
        epsilon=epsilon,
        name=f"{base_name}_obi",
    )
    return ema(obi_node, period=ema_period, name=base_name)
