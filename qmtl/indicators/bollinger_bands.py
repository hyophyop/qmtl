"""Bollinger Bands indicator."""

import math
from statistics import mean, pstdev

from qmtl.sdk.node import Node
from qmtl.sdk.cache_view import CacheView


def bollinger_bands(source: Node, window: int, multiplier: float = 2.0, *, name: str | None = None) -> Node:
    """Return a Node computing Bollinger Bands as (mid, upper, lower)."""

    def compute(view: CacheView):
        data = [v for _, v in view[source][source.interval][-window:]]
        if len(data) < window:
            return None
        mid = mean(data)
        std = pstdev(data)
        upper = mid + multiplier * std
        lower = mid - multiplier * std
        return {"mid": mid, "upper": upper, "lower": lower}

    return Node(
        input=source,
        compute_fn=compute,
        name=name or "bollinger_bands",
        interval=source.interval,
        period=window,
    )
