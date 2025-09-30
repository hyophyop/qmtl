"""Volatility indicator based on return standard deviation."""

from statistics import stdev
from typing import Sequence

from qmtl.runtime.sdk.node import Node
from qmtl.runtime.sdk.cache_view import CacheView


def volatility_node(source: Node, window: int, *, name: str | None = None) -> Node:
    """Return a Node computing the standard deviation of returns.

    The node calculates percentage returns between consecutive values of the
    ``source`` node and returns the sample standard deviation over ``window``
    returns.
    """

    def compute(view: CacheView):
        data = [v for _, v in view[source][source.interval][-(window + 1):]]
        if len(data) < window + 1:
            return None
        returns = [(data[i] / data[i - 1]) - 1 for i in range(1, len(data))]
        if len(returns) < 2:
            return 0.0
        return stdev(returns)

    return Node(
        input=source,
        compute_fn=compute,
        name=name or "volatility",
        interval=source.interval,
        period=window + 1,
    )


def volatility(values: Sequence[float]) -> float:
    """Return standard deviation of percentage returns for ``values``."""
    if len(values) < 2:
        return 0.0
    returns = [(values[i] / values[i - 1]) - 1 for i in range(1, len(values))]
    if len(returns) < 2:
        return 0.0
    return stdev(returns)


__all__ = ["volatility_node", "volatility"]
