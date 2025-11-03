"""Time Weighted Average Price indicator."""

from qmtl.runtime.sdk.cache_view import CacheView
from qmtl.runtime.sdk.node import Node

from .helpers import timestamp_weighted_average


def twap(price: Node, period: int, *, name: str | None = None) -> Node:
    """Return a Node computing the Time Weighted Average Price.

    The indicator samples the most recent ``period`` intervals, weighting each
    price by the elapsed time until the next observation. When the cache lacks
    sufficient data or the cumulative weight is zero the node emits ``None``.
    """

    window = max(period, 0) + 1

    def compute(view: CacheView):
        if period <= 0:
            return None

        series = view[price][price.interval][-window:]
        if len(series) < window:
            return None
        return timestamp_weighted_average(series)

    return Node(
        input=[price],
        compute_fn=compute,
        name=name or "twap",
        interval=price.interval,
        period=window,
    )

