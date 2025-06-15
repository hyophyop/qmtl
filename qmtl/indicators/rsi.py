"""Relative Strength Index indicator."""

from qmtl.sdk.node import Node
from qmtl.sdk.cache_view import CacheView


def rsi(source: Node, window: int, *, name: str | None = None) -> Node:
    """Return a Node computing the RSI."""

    def compute(view: CacheView):
        data = [v for _, v in view[source][source.interval][-(window + 1):]]
        if len(data) < window + 1:
            return None
        gains = []
        losses = []
        for i in range(1, len(data)):
            diff = data[i] - data[i - 1]
            if diff >= 0:
                gains.append(diff)
            else:
                losses.append(-diff)
        avg_gain = sum(gains) / window
        avg_loss = sum(losses) / window
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    return Node(
        input=source,
        compute_fn=compute,
        name=name or "rsi",
        interval=source.interval,
        period=window + 1,
    )
