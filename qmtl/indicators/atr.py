"""Average True Range indicator."""

from qmtl.sdk.node import Node
from qmtl.sdk.cache_view import CacheView


def atr(high: Node, low: Node, close: Node, window: int, *, name: str | None = None) -> Node:
    """Return a Node computing Average True Range."""

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
            tr = max(h - l, abs(h - pc), abs(l - pc))
            tr_values.append(tr)
        return sum(tr_values) / window

    return Node(
        input=[high, low, close],
        compute_fn=compute,
        name=name or "atr",
        interval=close.interval,
        period=window,
    )
