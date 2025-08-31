"""Fee model implementations."""

from __future__ import annotations

from dataclasses import dataclass

from .interfaces import FeeModel
from .order import Order


@dataclass
class PercentFeeModel(FeeModel):
    """Percentage-of-notional fees with a minimum."""

    rate: float = 0.001  # 0.1%
    minimum: float = 0.0

    def calculate(self, order: Order, fill_price: float) -> float:
        notional = abs(order.quantity) * fill_price
        return max(notional * self.rate, self.minimum)


@dataclass
class PerShareFeeModel(FeeModel):
    """Per-share fees with optional minimum/maximum caps."""

    fee_per_share: float = 0.01
    minimum: float = 0.0
    maximum: float | None = None

    def calculate(self, order: Order, fill_price: float) -> float:
        fee = abs(order.quantity) * self.fee_per_share
        if fee < self.minimum:
            fee = self.minimum
        if self.maximum is not None and fee > self.maximum:
            fee = self.maximum
        return fee


@dataclass
class CompositeFeeModel(FeeModel):
    """Combine multiple fee models by summing their outputs."""

    components: tuple[FeeModel, ...]

    def calculate(self, order: Order, fill_price: float) -> float:
        return sum(c.calculate(order, fill_price) for c in self.components)


@dataclass
class IBKRFeeModel(FeeModel):
    """Simplified Interactive Brokers-like per-share tiered fee model.

    Parameters
    ----------
    tiers : list[tuple[int, float]]
        Sorted ascending by share threshold; (threshold, fee_per_share).
        The highest tier applies beyond the last threshold.
    minimum : float
        Minimum fee per order.
    exchange_fees : float
        Flat per-order exchange/regulatory surcharge (very simplified).

    Notes
    -----
    This is a simplified approximation for backtests; real schedules vary by venue and product.
    """

    tiers: list[tuple[int, float]] = None
    minimum: float = 1.0
    exchange_fees: float = 0.0

    def __post_init__(self) -> None:
        if self.tiers is None:
            # Default: 0–300k: $0.0035, >300k: $0.0020
            self.tiers = [(300_000, 0.0035)]
            # Implicit last tier: 0.0020

    def calculate(self, order: Order, fill_price: float) -> float:
        shares = abs(order.quantity)
        remaining = shares
        total = 0.0
        last_rate = 0.0020
        prev_thresh = 0
        for thresh, rate in self.tiers:
            band = max(0, min(remaining, thresh - prev_thresh))
            if band > 0:
                total += band * rate
                remaining -= band
                prev_thresh = thresh
        if remaining > 0:
            total += remaining * last_rate
        # Apply minimum and exchange surcharges
        if total < self.minimum:
            total = self.minimum
        total += self.exchange_fees
        return total
