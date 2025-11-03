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
    "sum_recent_values",
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


def sum_recent_values(view: CacheView, node: Node, period: int) -> float | None:
    """Return the sum of the latest ``period`` values emitted by ``node``.

    The helper reads the data from ``view`` respecting the node's interval and
    ensures that ``period`` samples exist and are numerically coercible. When
    values are missing, malformed, or cannot be converted to ``float`` the
    helper returns ``None`` to signal that downstream indicators should skip
    the computation for that bar.
    """

    if period <= 0:
        return 0.0

    series = view[node][node.interval][-period:]
    if len(series) < period:
        return None

    total = 0.0
    for _, value in series:
        numeric = _to_float(value)
        if numeric is None:
            return None
        total += numeric
    return total


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
