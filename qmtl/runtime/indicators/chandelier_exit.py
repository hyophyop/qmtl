"""Chandelier Exit indicator."""

from qmtl.runtime.sdk.node import Node
from qmtl.runtime.sdk.cache_view import CacheView


def chandelier_exit(
    high: Node,
    low: Node,
    close: Node,
    *,
    period: int = 22,
    multiplier: float = 3.0,
    name: str | None = None,
) -> Node:
    """Return a Node computing Chandelier Exit levels."""

    def compute(view: CacheView):
        highs = view[high][high.interval][-period:]
        lows = view[low][low.interval][-period:]
        closes = view[close][close.interval][-(period + 1):]
        if len(highs) < period or len(lows) < period or len(closes) < period + 1:
            return None
        tr_values = []
        for i in range(1, period + 1):
            h = highs[i - 1][1]
            l = lows[i - 1][1]
            pc = closes[i - 1][1]
            tr_values.append(max(h - l, abs(h - pc), abs(l - pc)))
        atr_val = sum(tr_values) / period
        highest_high = max(v for _, v in highs)
        lowest_low = min(v for _, v in lows)
        long_exit = highest_high - multiplier * atr_val
        short_exit = lowest_low + multiplier * atr_val
        return {"long": long_exit, "short": short_exit}

    return Node(
        input=[high, low, close],
        compute_fn=compute,
        name=name or "chandelier_exit",
        interval=close.interval,
        period=period,
    )
