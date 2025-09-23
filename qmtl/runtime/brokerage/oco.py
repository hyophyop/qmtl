from __future__ import annotations

"""Utility for One-Cancels-Other order groups."""

from dataclasses import dataclass
from typing import Optional, Tuple

from .order import Order, Fill, Account
from .brokerage_model import BrokerageModel


@dataclass
class OCOOrder:
    """Container for an OCO (one-cancels-other) order pair.

    Orders are submitted sequentially. If the first order fills, the second is
    automatically cancelled and represented as a zero-quantity :class:`Fill`.
    """

    first: Order
    second: Order

    def execute(
        self,
        brokerage: BrokerageModel,
        account: Account,
        market_price: float,
        *,
        ts=None,
        bar_volume: Optional[int] = None,
    ) -> Tuple[Fill, Fill]:
        """Execute the OCO group and return fills for both orders.

        The unfilled leg is returned as a zero-quantity fill.
        """

        fill_first = brokerage.execute_order(
            account, self.first, market_price, ts=ts, bar_volume=bar_volume
        )
        if fill_first.quantity != 0:
            # Second leg cancelled
            return (
                fill_first,
                Fill(symbol=self.second.symbol, quantity=0, price=market_price),
            )

        fill_second = brokerage.execute_order(
            account, self.second, market_price, ts=ts, bar_volume=bar_volume
        )
        if fill_second.quantity != 0:
            # First leg cancelled
            return (
                Fill(symbol=self.first.symbol, quantity=0, price=market_price),
                fill_second,
            )

        return fill_first, fill_second
