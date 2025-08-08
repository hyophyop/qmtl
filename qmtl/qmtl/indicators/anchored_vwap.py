"""Anchored VWAP indicator."""

from qmtl.sdk.node import Node
from qmtl.sdk.cache_view import CacheView


def anchored_vwap(price: Node, volume: Node, anchor_ts: int, *, name: str | None = None) -> Node:
    """Return a Node computing VWAP anchored at ``anchor_ts``."""

    def compute(view: CacheView):
        prices = view[price][price.interval]
        vols = view[volume][volume.interval]
        filtered = [
            (p, v)
            for (t, p), (_, v) in zip(prices, vols)
            if t >= anchor_ts
        ]
        if not filtered:
            return None
        num = sum(p * v for p, v in filtered)
        den = sum(v for _, v in filtered)
        if den == 0:
            return None
        return num / den

    return Node(
        input=[price, volume],
        compute_fn=compute,
        name=name or "anchored_vwap",
        interval=price.interval,
        period=price.period,
    )
