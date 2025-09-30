"""Average True Range indicator."""

from qmtl.runtime.sdk.node import Node
from qmtl.runtime.sdk.cache_view import CacheView


def atr(high: Node, low: Node, close: Node, period: int, *, name: str | None = None) -> Node:
    """Return a Node computing Average True Range."""

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
            tr = max(h - l, abs(h - pc), abs(l - pc))
            tr_values.append(tr)
        return sum(tr_values) / period

    return Node(
        input=[high, low, close],
        compute_fn=compute,
        name=name or "atr",
        interval=close.interval,
        period=period,
    )
