"""Volume Weighted Average Price indicator."""

from qmtl.sdk.node import Node
from qmtl.sdk.cache_view import CacheView


def vwap(price: Node, volume: Node, period: int, *, name: str | None = None) -> Node:
    """Return a Node computing VWAP."""

    def compute(view: CacheView):
        prices = view[price][price.interval][-period:]
        vols = view[volume][volume.interval][-period:]
        if len(prices) < period or len(vols) < period:
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
        period=period,
    )
