"""Helper utilities for indicator nodes."""

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from qmtl.runtime.sdk.cache_view import CacheView
from qmtl.runtime.sdk.node import Node
from qmtl.runtime.transforms import alpha_history_node

__all__ = [
    "alpha_indicator_with_history",
    "extract_order_book_snapshot",
    "normalize_order_book_level_size",
    "iter_order_book_level_sizes",
    "sum_order_book_levels",
    "best_order_book_level",
    "weighted_average",
    "timestamp_weighted_average",
]


def extract_order_book_snapshot(view: CacheView, source: Node) -> Mapping[str, Any] | None:
    """Return the latest order-book snapshot emitted by ``source`` if available."""

    series = view[source][source.interval]
    latest = series.latest()
    if latest is None:
        return None

    snapshot = latest[1]
    if snapshot is None or not isinstance(snapshot, Mapping):
        return None
    return snapshot


def _to_float(value: Any) -> float | None:
    """Safely convert ``value`` to ``float`` when possible."""

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize_order_book_level_size(level: Any) -> float | None:
    """Extract the size component from a level entry."""

    if isinstance(level, Mapping):
        raw_size = level.get("size")
    elif isinstance(level, (list, tuple)):
        if not level:
            return None
        raw_size = level[1] if len(level) > 1 else level[0]
    else:
        raw_size = level
    return _to_float(raw_size)


def _normalize_order_book_level_price(level: Any) -> float | None:
    """Extract the price component from a level entry."""

    if isinstance(level, Mapping):
        raw_price = level.get("price")
    elif isinstance(level, (list, tuple)):
        if not level:
            return None
        raw_price = level[0]
    else:
        return None
    return _to_float(raw_price)


def best_order_book_level(
    levels_data: Sequence[Any] | None,
) -> tuple[float | None, float | None]:
    """Return the price and size of the best level in ``levels_data``."""

    if not levels_data:
        return None, None

    level = levels_data[0]
    price = _normalize_order_book_level_price(level)
    size = normalize_order_book_level_size(level)
    return price, size


def iter_order_book_level_sizes(levels_data: Sequence[Any] | None, levels: int) -> list[float]:
    """Return parsed sizes for up to ``levels`` order-book entries."""

    if not levels_data or levels <= 0:
        return []

    values: list[float] = []
    for level in levels_data:
        if len(values) >= levels:
            break
        size = normalize_order_book_level_size(level)
        if size is None:
            continue
        values.append(size)
    return values


def sum_order_book_levels(levels_data: Sequence[Any] | None, levels: int) -> float:
    """Return the summed depth over ``levels`` entries from ``levels_data``."""

    if levels <= 0:
        return 0.0
    return sum(iter_order_book_level_sizes(levels_data, levels))


def weighted_average(
    series: Sequence[tuple[Any, Any]] | None,
    weights: Sequence[Any] | None,
) -> float | None:
    """Return the weighted average for ``series`` using ``weights``.

    The helper safely skips entries that cannot be converted to ``float`` and
    ignores non-positive weights. ``None`` is returned when no valid
    contributions remain or the total weight collapses to zero.
    """

    if not series or not weights:
        return None

    total = 0.0
    total_weight = 0.0
    for (_, raw_value), raw_weight in zip(series, weights):
        value = _to_float(raw_value)
        weight = _to_float(raw_weight)
        if value is None or weight is None or weight <= 0:
            continue
        total += value * weight
        total_weight += weight

    if total_weight == 0:
        return None
    return total / total_weight


def timestamp_weighted_average(series: Sequence[tuple[Any, Any]] | None) -> float | None:
    """Return the time-weighted average over ``series``.

    Adjacent timestamp differences supply the weights, aligning each value with
    the following timestamp. When all gaps vanish or the sequence is shorter
    than two entries the function emits ``None``.
    """

    if not series or len(series) < 2:
        return None

    aligned: list[tuple[Any, Any]] = []
    weights: list[float] = []

    for current, nxt in zip(series, series[1:]):
        curr_ts, _ = current
        next_ts, _ = nxt
        delta = next_ts - curr_ts
        if hasattr(delta, "total_seconds"):
            delta = delta.total_seconds()
        weight = _to_float(delta)
        if weight is None or weight <= 0:
            continue
        aligned.append(current)
        weights.append(weight)

    if not aligned:
        return None

    return weighted_average(aligned, weights)


def alpha_indicator_with_history(
    compute_fn: Callable,
    inputs: Sequence[Node] | None = None,
    *,
    window: int = 20,
    interval: int | str = "1s",
    period: int = 1,
    name: str | None = None,
) -> Node:
    """Wrap ``compute_fn`` with ``alpha_history_node``.

    Parameters
    ----------
    compute_fn:
        Node processor returning a mapping with an ``"alpha"`` value.
    inputs:
        Upstream nodes supplying the inputs for ``compute_fn``.
    window:
        Number of recent alpha values retained in history.
    interval:
        Bar interval for the resulting node.
    period:
        Number of bars to retain in the cache.
    name:
        Optional name for the inner alpha node.

    Returns
    -------
    Node
        Node emitting a sliding window of alpha values.
    """

    def wrapped(view):
        result = compute_fn(view)
        return result.get("alpha")

    base = Node(
        input=list(inputs) if inputs else None,
        compute_fn=wrapped,
        name=name or compute_fn.__name__,
        interval=interval,
        period=period,
    )
    return alpha_history_node(base, window=window, name=f"{base.name}_history")
