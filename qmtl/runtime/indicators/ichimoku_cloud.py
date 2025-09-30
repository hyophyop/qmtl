"""Ichimoku Cloud indicator (simplified)."""

from qmtl.runtime.sdk.node import Node
from qmtl.runtime.sdk.cache_view import CacheView


def ichimoku_cloud(high: Node, low: Node, close: Node, *, name: str | None = None) -> Node:
    """Return a Node computing Ichimoku Cloud values."""

    def compute(view: CacheView):
        highs = [v for _, v in view[high][high.interval]]
        lows = [v for _, v in view[low][low.interval]]
        closes = [v for _, v in view[close][close.interval]]
        if len(highs) < 52 or len(lows) < 52 or len(closes) < 26:
            return None
        tenkan = (max(highs[-9:]) + min(lows[-9:])) / 2
        kijun = (max(highs[-26:]) + min(lows[-26:])) / 2
        senkou_a = (tenkan + kijun) / 2
        senkou_b = (max(highs[-52:]) + min(lows[-52:])) / 2
        chikou = closes[-26]
        return {
            "tenkan": tenkan,
            "kijun": kijun,
            "senkou_a": senkou_a,
            "senkou_b": senkou_b,
            "chikou": chikou,
        }

    return Node(
        input=[high, low, close],
        compute_fn=compute,
        name=name or "ichimoku_cloud",
        interval=close.interval,
        period=52,
    )
