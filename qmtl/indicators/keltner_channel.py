"""Keltner Channel indicator."""

from statistics import mean

from qmtl.sdk.node import Node
from qmtl.sdk.cache_view import CacheView


def keltner_channel(
    high: Node,
    low: Node,
    close: Node,
    *,
    ema_window: int = 20,
    atr_window: int = 10,
    multiplier: float = 2.0,
    name: str | None = None,
) -> Node:
    """Return a Node computing Keltner Channel (mid, upper, lower)."""

    alpha = 2 / (ema_window + 1)

    def compute(view: CacheView):
        highs = view[high][high.interval][-atr_window:]
        lows = view[low][low.interval][-atr_window:]
        closes = view[close][close.interval][-(max(ema_window, atr_window) + 1):]
        if (
            len(highs) < atr_window
            or len(lows) < atr_window
            or len(closes) < max(ema_window, atr_window) + 1
        ):
            return None
        # EMA
        ema_val = closes[-ema_window][1]
        for _, val in closes[-ema_window + 1 :]:
            ema_val = alpha * val + (1 - alpha) * ema_val
        # ATR
        tr_values = []
        for i in range(1, atr_window + 1):
            h = highs[i - 1][1]
            l = lows[i - 1][1]
            pc = closes[i - 1][1]
            tr = max(h - l, abs(h - pc), abs(l - pc))
            tr_values.append(tr)
        atr_val = sum(tr_values) / atr_window
        upper = ema_val + multiplier * atr_val
        lower = ema_val - multiplier * atr_val
        return {"mid": ema_val, "upper": upper, "lower": lower}

    return Node(
        input=[high, low, close],
        compute_fn=compute,
        name=name or "keltner_channel",
        interval=close.interval,
        period=max(ema_window, atr_window),
    )
