"""Stochastic transformation node."""

from qmtl.runtime.sdk.node import Node
from qmtl.runtime.sdk.cache_view import CacheView


def stochastic(source: Node, period: int, *, name: str | None = None) -> Node:
    """Return a Node computing stochastic oscillator over ``period`` values."""

    def compute(view: CacheView):
        values = [v for _, v in view[source][source.interval][-period:]]
        if len(values) < period:
            return None
        current = values[-1]
        lowest = min(values)
        highest = max(values)
        if highest == lowest:
            return 0.0
        return (current - lowest) / (highest - lowest) * 100

    return Node(
        input=source,
        compute_fn=compute,
        name=name or "stochastic",
        interval=source.interval,
        period=period,
    )
