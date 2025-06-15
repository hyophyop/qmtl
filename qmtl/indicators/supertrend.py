"""Supertrend indicator (simplified)."""

from qmtl.sdk.node import Node
from qmtl.sdk.cache_view import CacheView


def supertrend(
    high: Node,
    low: Node,
    close: Node,
    *,
    window: int = 10,
    multiplier: float = 3.0,
    name: str | None = None,
) -> Node:
    """Return a Node computing a simplified Supertrend value."""

    def compute(view: CacheView):
        highs = view[high][high.interval][-window:]
        lows = view[low][low.interval][-window:]
        closes = view[close][close.interval][-(window + 1):]
        if len(highs) < window or len(lows) < window or len(closes) < window + 1:
            return None
        tr_values = []
        for i in range(1, window + 1):
            h = highs[i - 1][1]
            l = lows[i - 1][1]
            pc = closes[i - 1][1]
            tr_values.append(max(h - l, abs(h - pc), abs(l - pc)))
        atr_val = sum(tr_values) / window
        mid = (highs[-1][1] + lows[-1][1]) / 2
        upper = mid + multiplier * atr_val
        lower = mid - multiplier * atr_val
        close_val = closes[-1][1]
        if close_val > upper:
            return lower
        if close_val < lower:
            return upper
        return lower if close_val > (upper + lower) / 2 else upper

    return Node(
        input=[high, low, close],
        compute_fn=compute,
        name=name or "supertrend",
        interval=close.interval,
        period=window,
    )
