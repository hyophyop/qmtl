"""Order-book imbalance indicator nodes."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from qmtl.runtime.sdk.cache_view import CacheView
from qmtl.runtime.sdk.node import Node

from .ema import ema
from .helpers import (
    extract_order_book_snapshot,
    iter_order_book_level_sizes,
    sum_order_book_levels,
)

__all__ = [
    "order_book_obi",
    "order_book_obi_ema",
    "order_book_imbalance_levels",
    "order_book_depth_slope",
    "order_book_obiL_and_slope",
    "priority_index",
]


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

    sizes = iter_order_book_level_sizes(levels_data, levels)
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

    bid_total = sum_order_book_levels(bids, levels)
    ask_total = sum_order_book_levels(asks, levels)

    if bid_total == 0.0 and ask_total == 0.0:
        return 0.0

    denominator = bid_total + ask_total + epsilon
    return (bid_total - ask_total) / denominator


def _is_sequence(value: Any) -> bool:
    """Return ``True`` when *value* is a non-string sequence."""

    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))


def _normalize_priority_value(rank: Any, size: Any) -> float | None:
    """Return normalized priority for a single queue entry."""

    try:
        rank_value = float(rank)
        size_value = float(size)
    except (TypeError, ValueError):
        return None

    if size_value <= 0:
        return None

    capped_rank = max(0.0, min(rank_value, size_value))
    normalized = 1.0 - (capped_rank / size_value)
    return max(0.0, min(1.0, normalized))


def _normalize_priority(rank: Any, size: Any) -> float | list[float | None] | None:
    """Normalize queue priority for scalar or sequence inputs."""

    rank_is_seq = _is_sequence(rank)
    size_is_seq = _is_sequence(size)

    if rank_is_seq or size_is_seq:
        if not (rank_is_seq and size_is_seq):
            return None

        try:
            rank_list = list(rank)  # type: ignore[arg-type]
            size_list = list(size)  # type: ignore[arg-type]
        except TypeError:
            return None

        if len(rank_list) != len(size_list):
            return None

        return [_normalize_priority_value(r, s) for r, s in zip(rank_list, size_list)]

    return _normalize_priority_value(rank, size)


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
        snapshot = extract_order_book_snapshot(view, source)
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


def priority_index(source: Node, *, name: str | None = None) -> Node:
    """Return a node computing normalized queue priority metadata.

    Snapshots emitted by ``source`` **must** provide ``queue_rank`` and
    ``queue_size`` keys. The values can be scalars or sequences with matching
    lengths. Ranks are assumed to be zero-indexed (``0`` means the front of the
    queue), and sizes must be positive. Missing keys raise ``ValueError``
    exceptions. When rank or size values cannot be parsed, or sizes are
    non-positive, the node returns ``None`` (or per-entry ``None`` values for
    batched inputs).
    """

    def compute(view: CacheView) -> float | list[float | None] | None:
        snapshot = extract_order_book_snapshot(view, source)
        if snapshot is None:
            return None

        if "queue_rank" not in snapshot:
            raise ValueError("priority_index requires 'queue_rank' in the snapshot")
        if "queue_size" not in snapshot:
            raise ValueError("priority_index requires 'queue_size' in the snapshot")

        rank = snapshot["queue_rank"]
        size = snapshot["queue_size"]

        return _normalize_priority(rank, size)

    return Node(
        input=source,
        compute_fn=compute,
        name=name or "priority_index",
        interval=source.interval,
        period=source.period or 1,
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
        snapshot = extract_order_book_snapshot(view, source)
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
        snapshot = extract_order_book_snapshot(view, source)
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
        snapshot = extract_order_book_snapshot(view, source)
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
