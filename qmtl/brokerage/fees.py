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

