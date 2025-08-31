"""Aggregate brokerage model combining component models."""

# Source: docs/architecture/lean_brokerage_model.md

from __future__ import annotations

from datetime import datetime
from typing import Optional

from .interfaces import BuyingPowerModel, FeeModel, SlippageModel, FillModel
from .order import Account, Order, Fill, OrderType, TimeInForce
from .symbols import SymbolPropertiesProvider
from .exchange_hours import ExchangeHoursProvider
from .shortable import ShortableProvider


class BrokerageModel:
    """Compose buying power, fee, slippage and fill models with pre-trade checks."""

    def __init__(
        self,
        buying_power_model: BuyingPowerModel,
        fee_model: FeeModel,
        slippage_model: SlippageModel,
        fill_model: FillModel,
        *,
        symbols: SymbolPropertiesProvider | None = None,
        hours: ExchangeHoursProvider | None = None,
        shortable: ShortableProvider | None = None,
    ) -> None:
        self.buying_power_model = buying_power_model
        self.fee_model = fee_model
        self.slippage_model = slippage_model
        self.fill_model = fill_model
        self.symbols = symbols
        self.hours = hours
        self.shortable = shortable

    def _validate_order_properties(self, order: Order) -> None:
        if self.symbols is not None:
            price_for_validation = order.limit_price if order.type in {OrderType.LIMIT, OrderType.STOP_LIMIT} else order.price
            self.symbols.validate_order(order.symbol, price_for_validation, order.quantity)

    def _validate_hours(self, ts: Optional[datetime]) -> None:
        if self.hours is None or ts is None:
            return
        if not self.hours.is_open(ts):
            raise ValueError("Market is closed per exchange hours policy")

    def _validate_shortable(self, order: Order, ts: Optional[datetime]) -> None:
        if self.shortable is None:
            return
        if order.quantity < 0:
            # Simplified: treat any sell as potentially short without positions context
            from datetime import date as _date
            if not self.shortable.is_shortable(order.symbol, on=_date.today() if ts is None else ts.date()):
                raise ValueError(f"Symbol {order.symbol} not shortable")

    def can_submit_order(self, account: Account, order: Order, *, ts: Optional[datetime] = None) -> bool:
        """Return True if the order passes symbol/hour/buying power checks."""

        # Symbol/tick/lot validation
        self._validate_order_properties(order)
        # Market hours validation (if configured)
        self._validate_hours(ts)
        # Shortability
        self._validate_shortable(order, ts)
        # Buying power validation
        return self.buying_power_model.has_sufficient_buying_power(account, order)

    def execute_order(self, account: Account, order: Order, market_price: float, *, ts: Optional[datetime] = None) -> Fill:
        """Execute ``order`` and update ``account`` cash balance.

        Applies slippage, fills via fill model, computes fees, and debits/credits cash.
        Time-in-force policy is enforced at fill model level. If no shares are
        filled, no fees are applied and no cash is moved.
        """

        if not self.can_submit_order(account, order, ts=ts):
            raise ValueError("Order rejected by pre-trade checks")

        price_with_slippage = self.slippage_model.apply(order, market_price)
        fill = self.fill_model.fill(order, price_with_slippage)

        if fill.quantity == 0:
            # Nothing executed
            fill.fee = 0.0
            return fill

        fee = self.fee_model.calculate(order, fill.price)
        fill.fee = fee
        # Use actual filled quantity for cash movement
        cost = fill.price * fill.quantity + fee
        account.cash -= cost
        return fill
