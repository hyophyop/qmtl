"""Placeholder Rough Bergomi-based indicator."""

import math
from qmtl.sdk.node import Node
from qmtl.sdk.cache_view import CacheView


def rough_bergomi(source: Node, window: int, *, name: str | None = None) -> Node:
    """Return a Node computing a simple rough volatility estimate."""

    def compute(view: CacheView):
        data = [v for _, v in view[source][source.interval][- (window + 1):]]
        if len(data) < window + 1:
            return None
        returns = [math.log(data[i] / data[i - 1]) for i in range(1, len(data))]
        if not returns:
            return None
        mean_ret = sum(returns) / len(returns)
        var = sum((r - mean_ret) ** 2 for r in returns) / len(returns)
        return math.sqrt(var)

    return Node(
        input=source,
        compute_fn=compute,
        name=name or "rough_bergomi",
        interval=source.interval,
        period=window + 1,
    )
