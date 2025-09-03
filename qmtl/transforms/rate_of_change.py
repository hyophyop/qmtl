from __future__ import annotations

"""Upstream rate-of-change transformation."""

from qmtl.sdk.node import Node
from qmtl.sdk.cache_view import CacheView


def rate_of_change(
    source: Node,
    *,
    interval: int | None = None,
    period: int = 2,
    name: str | None = None,
) -> Node:
    """Return a node computing percentage change over ``period`` values."""

    interval = interval or source.interval

    def compute(view: CacheView):
        data = view[source][interval][-period:]
        if len(data) < 2:
            return None
        start = data[0][1]
        end = data[-1][1]
        if start == 0:
            return None
        return (end - start) / start

    return Node(
        input=source,
        compute_fn=compute,
        name=name or "rate_of_change",
        interval=interval,
        period=period,
    )


def rate_of_change_series(values: list[float]) -> float:
    """Return percentage change between first and last value."""
    if len(values) < 2:
        return 0.0
    start = values[0]
    end = values[-1]
    if start == 0:
        return 0.0
    return (end - start) / start


__all__ = ["rate_of_change", "rate_of_change_series"]
