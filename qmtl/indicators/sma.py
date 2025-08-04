"""Simple moving average indicator."""

from qmtl.sdk.node import Node
from qmtl.sdk.cache_view import CacheView


def sma(source: Node, period: int, *, name: str | None = None) -> Node:
    """Return a Node computing a simple moving average over ``period`` values."""

    def compute(view: CacheView):
        data = view[source][source.interval][-period:]
        if not data:
            return None
        values = [v for _, v in data]
        return sum(values) / len(values)

    return Node(
        input=source,
        compute_fn=compute,
        name=name or "sma",
        interval=source.interval,
        period=period,
    )
