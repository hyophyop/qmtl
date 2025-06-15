"""KDJ oscillator indicator (simplified)."""

from qmtl.sdk.node import Node
from qmtl.sdk.cache_view import CacheView


def kdj(high: Node, low: Node, close: Node, window: int, *, name: str | None = None) -> Node:
    """Return a Node computing a simplified KDJ oscillator."""

    def compute(view: CacheView):
        highs = [v for _, v in view[high][high.interval][-window:]]
        lows = [v for _, v in view[low][low.interval][-window:]]
        closes = [v for _, v in view[close][close.interval][-1:]]
        if len(highs) < window or len(lows) < window or not closes:
            return None
        highest = max(highs)
        lowest = min(lows)
        if highest == lowest:
            rsv = 0.0
        else:
            rsv = (closes[-1] - lowest) / (highest - lowest) * 100
        # simplified K=D=J=RSV
        return {"K": rsv, "D": rsv, "J": rsv}

    return Node(
        input=[high, low, close],
        compute_fn=compute,
        name=name or "kdj",
        interval=close.interval,
        period=window,
    )
