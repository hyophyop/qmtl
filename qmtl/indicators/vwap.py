"""Volume Weighted Average Price indicator."""

from qmtl.sdk.node import Node
from qmtl.sdk.cache_view import CacheView


def vwap(price: Node, volume: Node, window: int, *, name: str | None = None) -> Node:
    """Return a Node computing VWAP."""

    def compute(view: CacheView):
        prices = view[price][price.interval][-window:]
        vols = view[volume][volume.interval][-window:]
        if len(prices) < window or len(vols) < window:
            return None
        num = sum(p[1] * v[1] for p, v in zip(prices, vols))
        den = sum(v[1] for v in vols)
        if den == 0:
            return None
        return num / den

    return Node(
        input=[price, volume],
        compute_fn=compute,
        name=name or "vwap",
        interval=price.interval,
        period=window,
    )
