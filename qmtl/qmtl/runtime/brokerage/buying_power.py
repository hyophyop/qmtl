"""Buying power model implementations."""

# Source: docs/architecture/lean_brokerage_model.md

from __future__ import annotations

from .interfaces import BuyingPowerModel
from .order import Account, Order, AccountType
from .settlement import SettlementModel
from .symbols import SymbolPropertiesProvider


class CashBuyingPowerModel(BuyingPowerModel):
    """Buying power limited by available cash in the order's currency."""

    def __init__(self, symbols: SymbolPropertiesProvider | None = None) -> None:
        self.symbols = symbols

    def has_sufficient_buying_power(self, account: Account, order: Order) -> bool:
        if order.quantity <= 0:
            return True
        currency = (
            self.symbols.get(order.symbol).currency
            if self.symbols is not None
            else account.base_currency
        )
        required = order.price * order.quantity
        leverage = account.leverage if account.type == AccountType.MARGIN else 1.0
        balance = account.cashbook.get(currency).balance * leverage
        free = balance - required
        required_free = account.required_free_buying_power_percent * balance
        return free >= required_free


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
        if order.quantity <= 0:
            return True
        currency = (
            self.symbols.get(order.symbol).currency
            if self.symbols is not None
            else account.base_currency
        )
        required = order.price * order.quantity
        leverage = account.leverage if account.type == AccountType.MARGIN else 1.0
        balance = self.settlement.available_cash(account, currency) * leverage
        free = balance - required
        required_free = account.required_free_buying_power_percent * balance
        return free >= required_free
