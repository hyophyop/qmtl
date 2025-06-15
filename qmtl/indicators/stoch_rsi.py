"""Stochastic RSI indicator."""

import math
from qmtl.sdk.node import Node
from qmtl.sdk.cache_view import CacheView


def stoch_rsi(source: Node, window: int, *, name: str | None = None) -> Node:
    """Return a Node computing Stochastic RSI."""

    def _rsi(values: list[float]) -> float:
        gains = []
        losses = []
        for i in range(1, len(values)):
            diff = values[i] - values[i - 1]
            if diff >= 0:
                gains.append(diff)
            else:
                losses.append(-diff)
        avg_gain = sum(gains) / (len(values) - 1)
        avg_loss = sum(losses) / (len(values) - 1)
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    def compute(view: CacheView):
        values = [v for _, v in view[source][source.interval][-(window * 2):]]
        if len(values) < window * 2:
            return None
        rsi_vals = [
            _rsi(values[i : i + window + 1]) for i in range(len(values) - window)
        ]
        current = rsi_vals[-1]
        lowest = min(rsi_vals)
        highest = max(rsi_vals)
        if highest == lowest:
            return 0.0
        return (current - lowest) / (highest - lowest) * 100

    return Node(
        input=source,
        compute_fn=compute,
        name=name or "stoch_rsi",
        interval=source.interval,
        period=window * 2,
    )
