"""Slippage model implementations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .interfaces import SlippageModel
from .order import Order


class NullSlippageModel(SlippageModel):
    """No slippage applied."""

    def apply(self, order: Order, market_price: float) -> float:
        return market_price


@dataclass
class ConstantSlippageModel(SlippageModel):
    """Apply fixed percentage slippage to market price."""

    pct: float = 0.0005

    def apply(self, order: Order, market_price: float) -> float:
        direction = 1 if order.quantity > 0 else -1
        return market_price + direction * market_price * self.pct


@dataclass
class SpreadBasedSlippageModel(SlippageModel):
    """Apply slippage equal to a fraction of a provided spread.

    Note: In absence of live bid/ask, users may precompute a proxy spread
    and pass it as `spread_hint` to `apply_price` helper.
    """

    spread_fraction: float = 0.5
    spread_hint: Optional[float] = None

    def apply(self, order: Order, market_price: float) -> float:
        spread = self.spread_hint or 0.0
        slip = (spread * self.spread_fraction)
        return market_price + (slip if order.quantity > 0 else -slip)


@dataclass
class VolumeShareSlippageModel(SlippageModel):
    """Volume-share slippage approximation.

    Uses simple quadratic form: impact = k * (q / vol)^2 * price
    if `bar_volume` is provided; otherwise falls back to constant pct.
    """

    k: float = 0.1
    bar_volume: Optional[float] = None
    fallback_pct: float = 0.0005

    def __init__(self, k: float = 0.1, bar_volume: Optional[float] = None, fallback_pct: float = 0.0005, **kwargs) -> None:
        # Backward-compat: support `slippage_rate` alias for fallback_pct
        if "slippage_rate" in kwargs and "fallback_pct" not in kwargs:
            fallback_pct = float(kwargs["slippage_rate"])
        self.k = k
        self.bar_volume = bar_volume
        self.fallback_pct = fallback_pct

    def apply(self, order: Order, market_price: float) -> float:
        if self.bar_volume and self.bar_volume > 0:
            ratio = abs(order.quantity) / float(self.bar_volume)
            impact = self.k * (ratio ** 2) * market_price
        else:
            impact = market_price * self.fallback_pct
        return market_price + (impact if order.quantity > 0 else -impact)
