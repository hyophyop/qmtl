"""Price change transformation node."""

from qmtl.runtime.sdk.node import Node
from qmtl.runtime.sdk.cache_view import CacheView


def price_change(
    source: Node,
    *,
    interval: int | None = None,
    period: int = 2,
    name: str | None = None,
) -> Node:
    """Return a node computing absolute price change over ``period`` values."""

    interval = interval or source.interval

    def compute(view: CacheView):
        data = view[source][interval][-period:]
        if len(data) < 2:
            return None
        start = data[0][1]
        end = data[-1][1]
        return end - start

    return Node(
        input=source,
        compute_fn=compute,
        name=name or "price_change",
        interval=interval,
        period=period,
    )


def price_delta(start: float, end: float) -> float:
    """Return absolute price change from ``start`` to ``end``."""
    return end - start


__all__ = ["price_change", "price_delta"]
