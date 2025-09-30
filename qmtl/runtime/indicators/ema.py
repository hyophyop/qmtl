"""Exponential moving average indicator."""

from qmtl.runtime.sdk.node import Node
from qmtl.runtime.sdk.cache_view import CacheView


def ema(source: Node, period: int, *, name: str | None = None) -> Node:
    """Return a Node computing an exponential moving average."""

    alpha = 2 / (period + 1)

    def compute(view: CacheView):
        data = [v for _, v in view[source][source.interval][-period:]]
        if len(data) < period:
            return None
        value = data[0]
        for x in data[1:]:
            value = alpha * x + (1 - alpha) * value
        return value

    return Node(
        input=source,
        compute_fn=compute,
        name=name or "ema",
        interval=source.interval,
        period=period,
    )
