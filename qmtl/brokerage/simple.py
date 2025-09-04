"""Simple brokerage model implementations."""

# Source: docs/architecture/lean_brokerage_model.md

from __future__ import annotations

from .interfaces import BuyingPowerModel, FeeModel, SlippageModel, FillModel
from .order import Account, Order, Fill
from .settlement import SettlementModel


class CashBuyingPowerModel(BuyingPowerModel):
    """Buying power limited by available cash."""

    def has_sufficient_buying_power(self, account: Account, order: Order) -> bool:
        required = order.price * order.quantity
        return account.cash >= required


class CashWithSettlementBuyingPowerModel(BuyingPowerModel):
    """Buying power that accounts for reserved cash in SettlementModel."""

    def __init__(self, settlement: SettlementModel) -> None:
        self.settlement = settlement

    def has_sufficient_buying_power(self, account: Account, order: Order) -> bool:
        required = order.price * order.quantity
        return self.settlement.available_cash(account) >= required


class ImmediateFillModel(FillModel):
    """Fill the entire order at the given price."""

    def fill(self, order: Order, market_price: float) -> Fill:
        return Fill(symbol=order.symbol, quantity=order.quantity, price=market_price)
