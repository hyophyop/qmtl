"""Stochastic transformation node."""

from qmtl.sdk.node import Node
from qmtl.sdk.cache_view import CacheView


def stochastic(source: Node, window: int, *, name: str | None = None) -> Node:
    """Return a Node computing stochastic oscillator over ``window`` values."""

    def compute(view: CacheView):
        values = [v for _, v in view[source][source.interval][-window:]]
        if len(values) < window:
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
        period=window,
    )
