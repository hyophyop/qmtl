"""On-Balance Volume indicator."""

from qmtl.sdk.node import Node
from qmtl.sdk.cache_view import CacheView


def obv(close: Node, volume: Node, *, name: str | None = None, window: int | None = None) -> Node:
    """Return a Node computing OBV over ``window`` entries if given."""

    def compute(view: CacheView):
        closes = list(view[close][close.interval])
        vols = list(view[volume][volume.interval])
        if window is not None:
            closes = closes[-(window + 1):]
            vols = vols[-(window + 1):]
        if len(closes) < 2 or len(vols) < 2:
            return None
        total = 0.0
        for i in range(1, min(len(closes), len(vols))):
            c_prev = closes[i - 1][1]
            c_curr = closes[i][1]
            v = vols[i][1]
            if c_curr > c_prev:
                total += v
            elif c_curr < c_prev:
                total -= v
        return total

    return Node(
        input=[close, volume],
        compute_fn=compute,
        name=name or "obv",
        interval=close.interval,
        period=window or 2,
    )
