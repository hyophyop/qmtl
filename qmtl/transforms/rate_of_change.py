"""Upstream rate-of-change transformation."""

from qmtl.sdk.node import Node
from .utils import create_period_delta_node


def rate_of_change(
    source: Node,
    *,
    interval: int | None = None,
    period: int = 2,
    name: str | None = None,
) -> Node:
    """Return a node computing percentage change over ``period`` values."""
    
    def percentage_change(start, end):
        if start == 0:
            return None
        return (end - start) / start
    
    return create_period_delta_node(
        source,
        percentage_change,
        interval=interval,
        period=period,
        name=name or "rate_of_change",
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
