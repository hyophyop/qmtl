"""Fee model implementations."""

from __future__ import annotations

from dataclasses import dataclass

from .interfaces import FeeModel
from .order import Order, OrderType


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


@dataclass
class MakerTakerFeeModel(FeeModel):
    """Apply different percentage rates for maker vs taker liquidity."""

    maker_rate: float = 0.0
    taker_rate: float = 0.001
    minimum: float = 0.0

    def calculate(self, order: Order, fill_price: float) -> float:
        rate = self.taker_rate if order.type == OrderType.MARKET else self.maker_rate
        notional = abs(order.quantity) * fill_price
        fee = notional * rate
        return fee if fee >= self.minimum else self.minimum


@dataclass
class TieredExchangeFeeModel(FeeModel):
    """Percentage-of-notional fees with rate tiers based on notional size."""

    tiers: list[tuple[float, float]] | None = None
    minimum: float = 0.0

    def __post_init__(self) -> None:
        if self.tiers is None:
            # Default two-tier schedule: <=50k notional 0.1%, otherwise 0.05%
            self.tiers = [(50_000.0, 0.001)]

    def calculate(self, order: Order, fill_price: float) -> float:
        notional = abs(order.quantity) * fill_price
        rate = self.tiers[-1][1]
        for threshold, tier_rate in self.tiers:
            if notional <= threshold:
                rate = tier_rate
                break
        fee = notional * rate
        return fee if fee >= self.minimum else self.minimum


@dataclass
class BorrowFeeModel(FeeModel):
    """Simple borrow fee applied on short sales."""

    rate: float = 0.0001

    def calculate(self, order: Order, fill_price: float) -> float:
        if order.quantity >= 0:
            return 0.0
        notional = abs(order.quantity) * fill_price
        return notional * self.rate
