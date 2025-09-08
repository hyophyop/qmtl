"""Buying power model implementations."""

# Source: docs/architecture/lean_brokerage_model.md

from __future__ import annotations

from .interfaces import BuyingPowerModel
from .order import Account, Order
from .settlement import SettlementModel
from .symbols import SymbolPropertiesProvider


class CashBuyingPowerModel(BuyingPowerModel):
    """Buying power limited by available cash in the order's currency."""

    def __init__(self, symbols: SymbolPropertiesProvider | None = None) -> None:
        self.symbols = symbols

    def has_sufficient_buying_power(self, account: Account, order: Order) -> bool:
        currency = (
            self.symbols.get(order.symbol).currency
            if self.symbols is not None
            else account.base_currency
        )
        required = order.price * order.quantity
        return account.cashbook.get(currency).balance >= required


class CashWithSettlementBuyingPowerModel(BuyingPowerModel):
    """Buying power that accounts for reserved cash in :class:`SettlementModel`."""

    def __init__(
        self,
        settlement: SettlementModel,
        symbols: SymbolPropertiesProvider | None = None,
    ) -> None:
        self.settlement = settlement
        self.symbols = symbols

    def has_sufficient_buying_power(self, account: Account, order: Order) -> bool:
        currency = (
            self.symbols.get(order.symbol).currency
            if self.symbols is not None
            else account.base_currency
        )
        required = order.price * order.quantity
        return self.settlement.available_cash(account, currency) >= required
