"""Price change transformation node."""

from qmtl.sdk.node import Node
from .utils import create_period_delta_node


def price_change(
    source: Node,
    *,
    interval: int | None = None,
    period: int = 2,
    name: str | None = None,
) -> Node:
    """Return a node computing absolute price change over ``period`` values."""
    
    def absolute_change(start, end):
        return end - start
    
    return create_period_delta_node(
        source,
        absolute_change,
        interval=interval,
        period=period,
        name=name or "price_change",
    )


def price_delta(start: float, end: float) -> float:
    """Return absolute price change from ``start`` to ``end``."""
    return end - start


__all__ = ["price_change", "price_delta"]
