"""Fill model implementations for different order types and TIF policies."""

# Source: docs/architecture/lean_brokerage_model.md

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .interfaces import FillModel
from .order import Order, Fill, OrderType, TimeInForce


class ImmediateFillModel(FillModel):
    """Fill the entire order at the given price."""

    def fill(self, order: Order, market_price: float) -> Fill:
        return Fill(symbol=order.symbol, quantity=order.quantity, price=market_price)


@dataclass
class BaseFillModel(FillModel):
    """Base fill model with optional liquidity cap for IOC partials.

    Parameters
    ----------
    liquidity_cap : Optional[int]
        If set, represents the max shares that can be filled immediately.
        This enables simple IOC partial behavior without a full order book.
    """

    liquidity_cap: Optional[int] = None

    def _apply_tif(self, order: Order, desired_qty: int) -> int:
        """Apply simple TIF semantics to the computed desired quantity.

        - FOK: require full fill, otherwise 0
        - IOC: fill up to `liquidity_cap` (if set) or desired quantity
        - DAY/GTC: take desired quantity
        """

        if desired_qty <= 0:
            return 0

        if order.tif == TimeInForce.FOK:
            return desired_qty if (self.liquidity_cap is None or desired_qty <= self.liquidity_cap) else 0

        if order.tif == TimeInForce.IOC:
            if self.liquidity_cap is None:
                return desired_qty
            return min(desired_qty, self.liquidity_cap)

        # DAY/GTC
        return desired_qty


class MarketFillModel(BaseFillModel):
    """Market orders fill immediately at the given market price."""

    def fill(self, order: Order, market_price: float) -> Fill:
        qty = self._apply_tif(order, abs(order.quantity))
        qty = qty if order.quantity >= 0 else -qty
        return Fill(symbol=order.symbol, quantity=qty, price=market_price)


class LimitFillModel(BaseFillModel):
    """Limit orders fill when price crosses the limit."""

    def fill(self, order: Order, market_price: float) -> Fill:
        if order.limit_price is None:
            # No limit specified, cannot fill
            return Fill(symbol=order.symbol, quantity=0, price=market_price)

        can_fill = False
        if order.quantity > 0:
            # Buy: market must be <= limit
            can_fill = market_price <= order.limit_price
        else:
            # Sell: market must be >= limit
            can_fill = market_price >= order.limit_price

        if not can_fill:
            return Fill(symbol=order.symbol, quantity=0, price=market_price)

        qty = self._apply_tif(order, abs(order.quantity))
        qty = qty if order.quantity >= 0 else -qty
        # Fill at min/max of market and limit to be conservative
        price = min(market_price, order.limit_price) if order.quantity > 0 else max(market_price, order.limit_price)
        return Fill(symbol=order.symbol, quantity=qty, price=price)


class StopMarketFillModel(BaseFillModel):
    """Stop orders trigger at the stop price and then execute at market."""

    def fill(self, order: Order, market_price: float) -> Fill:
        if order.stop_price is None:
            return Fill(symbol=order.symbol, quantity=0, price=market_price)

        triggered = False
        if order.quantity > 0:
            # Buy stop triggers when price >= stop
            triggered = market_price >= order.stop_price
        else:
            # Sell stop triggers when price <= stop
            triggered = market_price <= order.stop_price

        if not triggered:
            return Fill(symbol=order.symbol, quantity=0, price=market_price)

        qty = self._apply_tif(order, abs(order.quantity))
        qty = qty if order.quantity >= 0 else -qty
        return Fill(symbol=order.symbol, quantity=qty, price=market_price)


class StopLimitFillModel(BaseFillModel):
    """Stop-limit triggers at stop, then uses limit for execution."""

    def fill(self, order: Order, market_price: float) -> Fill:
        if order.stop_price is None or order.limit_price is None:
            return Fill(symbol=order.symbol, quantity=0, price=market_price)

        triggered = False
        if order.quantity > 0:
            triggered = market_price >= order.stop_price
        else:
            triggered = market_price <= order.stop_price

        if not triggered:
            return Fill(symbol=order.symbol, quantity=0, price=market_price)

        # After trigger, behave like limit
        lfm = LimitFillModel(liquidity_cap=self.liquidity_cap)
        return lfm.fill(order, market_price)


class UnifiedFillModel(FillModel):
    """Dispatch to the appropriate fill model by order type.

    This adapter enables a single ``FillModel`` to support multiple
    order types, mirroring how backtest engines route orders to
    different handlers. It preserves the simple IOC/FOK behavior via
    the ``liquidity_cap`` knob on ``BaseFillModel`` derivatives.
    """

    def __init__(self, *, liquidity_cap: Optional[int] = None) -> None:
        self._market = MarketFillModel(liquidity_cap=liquidity_cap)
        self._limit = LimitFillModel(liquidity_cap=liquidity_cap)
        self._stop = StopMarketFillModel(liquidity_cap=liquidity_cap)
        self._stop_limit = StopLimitFillModel(liquidity_cap=liquidity_cap)

    def fill(self, order: Order, market_price: float) -> Fill:
        if order.type == OrderType.MARKET:
            return self._market.fill(order, market_price)
        if order.type == OrderType.LIMIT:
            return self._limit.fill(order, market_price)
        if order.type == OrderType.STOP:
            return self._stop.fill(order, market_price)
        if order.type == OrderType.STOP_LIMIT:
            return self._stop_limit.fill(order, market_price)
        # Fallback: no fill
        return Fill(symbol=order.symbol, quantity=0, price=market_price)
