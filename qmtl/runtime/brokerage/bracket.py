from __future__ import annotations

"""Bracket order helper built atop :class:`OCOOrder`."""

from dataclasses import dataclass, replace
from typing import Optional, Tuple

from .order import Order, Fill, Account
from .brokerage_model import BrokerageModel
from .oco import OCOOrder


@dataclass
class BracketOrder:
    """Container for entry with attached take-profit and stop-loss exits.

    The entry order executes first. After shares are filled, an
    :class:`OCOOrder` of take-profit and stop-loss orders is created sized to
    the cumulative filled quantity. Subsequent calls adjust the exit orders
    if additional partial fills arrive. The bracket completes when either exit
    leg fills, automatically cancelling the opposite leg.
    """

    entry: Order
    take_profit: Order
    stop_loss: Order
    oco: Optional[OCOOrder] = None
    filled_qty: int = 0

    def execute(
        self,
        brokerage: BrokerageModel,
        account: Account,
        market_price: float,
        *,
        ts=None,
        bar_volume: Optional[int] = None,
    ) -> Tuple[Fill, Fill, Fill]:
        """Execute the bracket and return fills for entry and both exit legs."""

        # Submit remaining entry quantity if any
        fill_entry = Fill(symbol=self.entry.symbol, quantity=0, price=market_price)
        remaining = self.entry.quantity - self.filled_qty
        if remaining != 0:
            entry_order = replace(self.entry, quantity=remaining)
            fill_entry = brokerage.execute_order(
                account, entry_order, market_price, ts=ts, bar_volume=bar_volume
            )
            if fill_entry.quantity != 0:
                self.filled_qty += fill_entry.quantity
                qty = -self.filled_qty
                tp = replace(self.take_profit, quantity=qty)
                sl = replace(self.stop_loss, quantity=qty)
                self.oco = OCOOrder(tp, sl)

        # Execute exits if OCO active
        if self.oco is not None:
            fill_tp, fill_sl = self.oco.execute(
                brokerage, account, market_price, ts=ts, bar_volume=bar_volume
            )
            if fill_tp.quantity != 0 or fill_sl.quantity != 0:
                # Bracket completed
                self.oco = None
        else:
            fill_tp = Fill(symbol=self.take_profit.symbol, quantity=0, price=market_price)
            fill_sl = Fill(symbol=self.stop_loss.symbol, quantity=0, price=market_price)

        return fill_entry, fill_tp, fill_sl
