"""Simple brokerage model implementations."""

# Source: docs/architecture/lean_brokerage_model.md

from __future__ import annotations

from .interfaces import BuyingPowerModel, FeeModel, SlippageModel, FillModel
from .order import Account, Order, Fill


class CashBuyingPowerModel(BuyingPowerModel):
    """Buying power limited by available cash."""

    def has_sufficient_buying_power(self, account: Account, order: Order) -> bool:
        required = order.price * order.quantity
        return account.cash >= required


class PerShareFeeModel(FeeModel):
    """Deprecated: use qmtl.brokerage.fees.PerShareFeeModel instead."""

    def __init__(self, fee_per_share: float = 0.01) -> None:
        self.fee_per_share = fee_per_share

    def calculate(self, order: Order, fill_price: float) -> float:
        return abs(order.quantity) * self.fee_per_share


class VolumeShareSlippageModel(SlippageModel):
    """Deprecated: use qmtl.brokerage.slippage.VolumeShareSlippageModel."""

    def __init__(self, slippage_rate: float = 0.0005) -> None:
        self.slippage_rate = slippage_rate

    def apply(self, order: Order, market_price: float) -> float:
        direction = 1 if order.quantity > 0 else -1
        return market_price + direction * market_price * self.slippage_rate


class ImmediateFillModel(FillModel):
    """Fill the entire order at the given price."""

    def fill(self, order: Order, market_price: float) -> Fill:
        return Fill(symbol=order.symbol, quantity=order.quantity, price=market_price)
