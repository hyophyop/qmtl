"""Relative Strength Index indicator."""

from qmtl.runtime.sdk.node import Node
from qmtl.runtime.sdk.cache_view import CacheView


def rsi(source: Node, period: int, *, name: str | None = None) -> Node:
    """Return a Node computing the RSI."""

    def compute(view: CacheView):
        data = [v for _, v in view[source][source.interval][-(period + 1):]]
        if len(data) < period + 1:
            return None
        gains = []
        losses = []
        for i in range(1, len(data)):
            diff = data[i] - data[i - 1]
            if diff >= 0:
                gains.append(diff)
            else:
                losses.append(-diff)
        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    return Node(
        input=source,
        compute_fn=compute,
        name=name or "rsi",
        interval=source.interval,
        period=period + 1,
    )
