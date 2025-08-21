"""Aggregate brokerage model combining component models."""

# Source: docs/architecture/lean_brokerage_model.md

from __future__ import annotations

from .interfaces import BuyingPowerModel, FeeModel, SlippageModel, FillModel
from .order import Account, Order, Fill


class BrokerageModel:
    """Compose buying power, fee, slippage and fill models."""

    def __init__(
        self,
        buying_power_model: BuyingPowerModel,
        fee_model: FeeModel,
        slippage_model: SlippageModel,
        fill_model: FillModel,
    ) -> None:
        self.buying_power_model = buying_power_model
        self.fee_model = fee_model
        self.slippage_model = slippage_model
        self.fill_model = fill_model

    def can_submit_order(self, account: Account, order: Order) -> bool:
        """Return ``True`` if the order passes buying power checks."""

        return self.buying_power_model.has_sufficient_buying_power(account, order)

    def execute_order(self, account: Account, order: Order, market_price: float) -> Fill:
        """Execute ``order`` and update ``account`` cash balance."""

        if not self.can_submit_order(account, order):
            raise ValueError("Insufficient buying power")

        price_with_slippage = self.slippage_model.apply(order, market_price)
        fill = self.fill_model.fill(order, price_with_slippage)
        fee = self.fee_model.calculate(order, fill.price)
        fill.fee = fee
        cost = fill.price * order.quantity + fee
        account.cash -= cost
        return fill
