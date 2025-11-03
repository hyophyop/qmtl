"""Volume Weighted Average Price indicator."""

from qmtl.runtime.sdk.node import Node
from qmtl.runtime.sdk.cache_view import CacheView

from .helpers import weighted_average


def vwap(price: Node, volume: Node, period: int, *, name: str | None = None) -> Node:
    """Return a Node computing VWAP."""

    def compute(view: CacheView):
        prices = view[price][price.interval][-period:]
        vols = view[volume][volume.interval][-period:]
        if len(prices) < period or len(vols) < period:
            return None
        weights = [entry[1] for entry in vols]
        return weighted_average(prices, weights)

    return Node(
        input=[price, volume],
        compute_fn=compute,
        name=name or "vwap",
        interval=price.interval,
        period=period,
    )
