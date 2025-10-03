"""Order-book imbalance indicator nodes."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from qmtl.runtime.sdk.cache_view import CacheView
from qmtl.runtime.sdk.node import Node

from .ema import ema

__all__ = [
    "order_book_obi",
    "order_book_obi_ema",
    "order_book_imbalance_levels",
    "order_book_depth_slope",
    "order_book_obiL_and_slope",
]


def _extract_snapshot(view: CacheView, source: Node) -> Mapping[str, Any] | None:
    """Return the latest order-book snapshot from ``source`` if available."""

    series = view[source][source.interval]
    latest = series.latest()
    if latest is None:
        return None

    snapshot = latest[1]
    if snapshot is None or not isinstance(snapshot, Mapping):
        return None
    return snapshot


def _normalize_level_size(level: Any) -> float | None:
    """Extract the size component from a level entry."""

    if isinstance(level, (list, tuple)):
        if not level:
            return None
        raw_size = level[1] if len(level) > 1 else level[0]
    else:
        raw_size = level
    try:
        return float(raw_size)
    except (TypeError, ValueError):
        return None


def _iter_level_sizes(levels_data: Sequence[Any] | None, levels: int) -> list[float]:
    """Return parsed sizes for up to ``levels`` order-book entries."""

    if not levels_data or levels <= 0:
        return []

    values: list[float] = []
    for level in levels_data:
        if len(values) >= levels:
            break
        size = _normalize_level_size(level)
        if size is None:
            continue
        values.append(size)
    return values


def _sum_levels(levels_data: Sequence[Any] | None, levels: int) -> float:
    """Return the summed depth over ``levels`` entries from ``levels_data``."""

    if levels <= 0:
        return 0.0
    return sum(_iter_level_sizes(levels_data, levels))


def _compute_linear_slope(values: Sequence[float]) -> float:
    """Return the slope of a simple least-squares fit over ``values``."""

    count = len(values)
    if count == 0:
        return 0.0

    # 1-indexed positions provide a natural depth ordering.
    x_mean = (count + 1) / 2
    y_mean = sum(values) / count

    numerator = 0.0
    denominator = 0.0
    for idx, value in enumerate(values, start=1):
        dx = idx - x_mean
        numerator += dx * (value - y_mean)
        denominator += dx * dx

    if denominator == 0.0:
        return 0.0
    return numerator / denominator


def _depth_slope(levels_data: Sequence[Any] | None, levels: int, method: str) -> float:
    """Compute a slope describing how depth evolves across order-book levels."""

    normalized_method = method.lower()
    if normalized_method != "linear":
        raise ValueError(
            f"Unsupported depth slope method '{method}'. Only 'linear' is available."
        )

    sizes = _iter_level_sizes(levels_data, levels)
    if not sizes:
        return 0.0

    cumulative: list[float] = []
    running_total = 0.0
    for size in sizes:
        running_total += size
        cumulative.append(running_total)

    return _compute_linear_slope(cumulative)


def _compute_obi(
    bids: Sequence[Any] | None,
    asks: Sequence[Any] | None,
    levels: int,
    epsilon: float,
) -> float:
    """Helper returning the normalized imbalance across ``levels`` tiers."""

    bid_total = _sum_levels(bids, levels)
    ask_total = _sum_levels(asks, levels)

    if bid_total == 0.0 and ask_total == 0.0:
        return 0.0

    denominator = bid_total + ask_total + epsilon
    return (bid_total - ask_total) / denominator


def order_book_obi(
    source: Node,
    *,
    levels: int = 1,
    epsilon: float = 1e-9,
    period: int = 1,
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
    period:
        Number of recent outputs retained in the node cache. Defaults to 1.
    name:
        Optional node name. Defaults to ``"order_book_obi"``.
    """

    def compute(view: CacheView) -> float | None:
        snapshot = _extract_snapshot(view, source)
        if snapshot is None:
            return None

        bids = snapshot.get("bids", [])
        asks = snapshot.get("asks", [])

        return _compute_obi(bids, asks, levels, epsilon)

    return Node(
        input=source,
        compute_fn=compute,
        name=name or "order_book_obi",
        interval=source.interval,
        period=max(1, period),
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
        period=max(1, ema_period),
        name=f"{base_name}_obi",
    )
    return ema(obi_node, period=ema_period, name=base_name)


def order_book_imbalance_levels(
    source: Node,
    *,
    levels: int = 5,
    epsilon: float = 1e-9,
    period: int = 1,
    name: str | None = None,
) -> Node:
    """Return an ``OBI_L`` node aggregating the top ``levels`` depth tiers."""

    def compute(view: CacheView) -> float | None:
        snapshot = _extract_snapshot(view, source)
        if snapshot is None:
            return None

        return _compute_obi(snapshot.get("bids"), snapshot.get("asks"), levels, epsilon)

    return Node(
        input=source,
        compute_fn=compute,
        name=name or "order_book_imbalance_levels",
        interval=source.interval,
        period=max(1, period),
    )


def order_book_depth_slope(
    source: Node,
    *,
    levels: int = 5,
    method: str = "linear",
    period: int = 1,
    name: str | None = None,
) -> Node:
    """Return a node emitting the bid/ask depth slope across ``levels`` tiers."""

    def compute(view: CacheView) -> dict[str, float] | None:
        snapshot = _extract_snapshot(view, source)
        if snapshot is None:
            return None

        bids = snapshot.get("bids")
        asks = snapshot.get("asks")

        return {
            "bid_slope": _depth_slope(bids, levels, method),
            "ask_slope": _depth_slope(asks, levels, method),
        }

    return Node(
        input=source,
        compute_fn=compute,
        name=name or "order_book_depth_slope",
        interval=source.interval,
        period=max(1, period),
    )


def order_book_obiL_and_slope(
    source: Node,
    *,
    levels: int = 5,
    epsilon: float = 1e-9,
    method: str = "linear",
    period: int = 1,
    name: str | None = None,
) -> Node:
    """Return a combined node exposing ``OBI_L`` and depth slope features."""

    def compute(view: CacheView) -> dict[str, float] | None:
        snapshot = _extract_snapshot(view, source)
        if snapshot is None:
            return None

        bids = snapshot.get("bids")
        asks = snapshot.get("asks")

        obi_value = _compute_obi(bids, asks, levels, epsilon)
        return {
            "obi_l": obi_value,
            "bid_slope": _depth_slope(bids, levels, method),
            "ask_slope": _depth_slope(asks, levels, method),
        }

    return Node(
        input=source,
        compute_fn=compute,
        name=name or "order_book_obiL_and_slope",
        interval=source.interval,
        period=max(1, period),
    )
