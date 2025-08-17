"""Volume-based features: moving average and standard deviation."""

import math

from qmtl.sdk.node import Node
from qmtl.sdk.cache_view import CacheView


def volume_features(source: Node, period: int, *, name: str | None = None) -> Node:
    """Return a Node computing volume moving average and std over ``period`` values."""

    def compute(view: CacheView):
        values = [v for _, v in view[source][source.interval][-period:]]
        if len(values) < period:
            return None
        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / len(values)
        std = math.sqrt(variance)
        return {"volume_hat": mean, "volume_std": std}

    return Node(
        input=source,
        compute_fn=compute,
        name=name or "volume_features",
        interval=source.interval,
        period=period,
    )
