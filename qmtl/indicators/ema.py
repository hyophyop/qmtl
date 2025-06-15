"""Exponential moving average indicator."""

from qmtl.sdk.node import Node
from qmtl.sdk.cache_view import CacheView


def ema(source: Node, window: int, *, name: str | None = None) -> Node:
    """Return a Node computing an exponential moving average."""

    alpha = 2 / (window + 1)

    def compute(view: CacheView):
        data = [v for _, v in view[source][source.interval][-window:]]
        if len(data) < window:
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
        period=window,
    )
