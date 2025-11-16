"""Fill model implementations for different order types and TIF policies."""

# Source: docs/architecture/lean_brokerage_model.md

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from .interfaces import FillModel
from .order import Order, Fill, OrderType, TimeInForce


class ImmediateFillModel(FillModel):
    """Fill the entire order at the given price."""

    def fill(
        self,
        order: Order,
        market_price: float,
        *,
        ts: Optional[datetime] = None,
        exchange_hours=None,
        bar_volume: Optional[int] = None,
    ) -> Fill:
        return Fill(symbol=order.symbol, quantity=order.quantity, price=market_price)


@dataclass
class BaseFillModel(FillModel):
    """Base fill model with optional liquidity or volume caps for partial fills.

    Parameters
    ----------
    liquidity_cap : Optional[int]
        Absolute share cap that can be filled immediately.
    volume_limit : Optional[float]
        Fractional cap of the latest bar volume that can be filled.
    """

    liquidity_cap: Optional[int] = None
    volume_limit: Optional[float] = None

    def _apply_tif(
        self,
        order: Order,
        desired_qty: int,
        ts: Optional[datetime] = None,
        bar_volume: Optional[int] = None,
    ) -> int:
        """Apply simple TIF semantics to the computed desired quantity."""

        if desired_qty <= 0:
            return 0

        available = self._cap_available(desired_qty, bar_volume)
        return self._apply_time_in_force(order, desired_qty, available, ts)

    def _cap_available(self, desired_qty: int, bar_volume: Optional[int]) -> int:
        available = desired_qty
        if self.volume_limit is not None and bar_volume is not None:
            available = min(available, int(self.volume_limit * bar_volume))
        if self.liquidity_cap is not None:
            available = min(available, self.liquidity_cap)
        return available

    def _apply_time_in_force(
        self,
        order: Order,
        desired_qty: int,
        available: int,
        ts: Optional[datetime],
    ) -> int:
        tif_handlers = {
            TimeInForce.FOK: lambda: desired_qty if desired_qty <= available else 0,
            TimeInForce.IOC: lambda: available,
            TimeInForce.GTD: lambda: 0
            if order.expire_at is not None and ts is not None and ts > order.expire_at
            else min(desired_qty, available),
        }

        handler = tif_handlers.get(order.tif)
        if handler is not None:
            return handler()

        return min(desired_qty, available)


class MarketFillModel(BaseFillModel):
    """Market orders fill immediately at the given market price."""

    def fill(
        self,
        order: Order,
        market_price: float,
        *,
        ts: Optional[datetime] = None,
        exchange_hours=None,
        bar_volume: Optional[int] = None,
    ) -> Fill:
        qty = self._apply_tif(order, abs(order.quantity), ts, bar_volume)
        qty = qty if order.quantity >= 0 else -qty
        return Fill(symbol=order.symbol, quantity=qty, price=market_price)


class LimitFillModel(BaseFillModel):
    """Limit orders fill when price crosses the limit."""

    def fill(
        self,
        order: Order,
        market_price: float,
        *,
        ts: Optional[datetime] = None,
        exchange_hours=None,
        bar_volume: Optional[int] = None,
    ) -> Fill:
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

        qty = self._apply_tif(order, abs(order.quantity), ts, bar_volume)
        qty = qty if order.quantity >= 0 else -qty
        # Fill at min/max of market and limit to be conservative
        price = min(market_price, order.limit_price) if order.quantity > 0 else max(market_price, order.limit_price)
        return Fill(symbol=order.symbol, quantity=qty, price=price)


class StopMarketFillModel(BaseFillModel):
    """Stop orders trigger at the stop price and then execute at market."""

    def fill(
        self,
        order: Order,
        market_price: float,
        *,
        ts: Optional[datetime] = None,
        exchange_hours=None,
        bar_volume: Optional[int] = None,
    ) -> Fill:
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

        qty = self._apply_tif(order, abs(order.quantity), ts, bar_volume)
        qty = qty if order.quantity >= 0 else -qty
        return Fill(symbol=order.symbol, quantity=qty, price=market_price)


class StopLimitFillModel(BaseFillModel):
    """Stop-limit triggers at stop, then uses limit for execution."""

    def fill(
        self,
        order: Order,
        market_price: float,
        *,
        ts: Optional[datetime] = None,
        exchange_hours=None,
        bar_volume: Optional[int] = None,
    ) -> Fill:
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
        lfm = LimitFillModel(liquidity_cap=self.liquidity_cap, volume_limit=self.volume_limit)
        return lfm.fill(order, market_price, ts=ts, exchange_hours=exchange_hours, bar_volume=bar_volume)


class MarketOnOpenFillModel(BaseFillModel):
    """Market-on-open orders fill at the regular session open."""

    def fill(
        self,
        order: Order,
        market_price: float,
        *,
        ts: Optional[datetime] = None,
        exchange_hours=None,
        bar_volume: Optional[int] = None,
    ) -> Fill:
        if ts is None or exchange_hours is None:
            return Fill(symbol=order.symbol, quantity=0, price=market_price)
        if ts.time() != exchange_hours.market_hours.regular_start:
            return Fill(symbol=order.symbol, quantity=0, price=market_price)
        qty = self._apply_tif(order, abs(order.quantity), ts, bar_volume)
        qty = qty if order.quantity >= 0 else -qty
        return Fill(symbol=order.symbol, quantity=qty, price=market_price)


class MarketOnCloseFillModel(BaseFillModel):
    """Market-on-close orders fill at the regular session close."""

    def fill(
        self,
        order: Order,
        market_price: float,
        *,
        ts: Optional[datetime] = None,
        exchange_hours=None,
        bar_volume: Optional[int] = None,
    ) -> Fill:
        if ts is None or exchange_hours is None:
            return Fill(symbol=order.symbol, quantity=0, price=market_price)
        close_time = exchange_hours.early_closes.get(
            ts.date(), exchange_hours.market_hours.regular_end
        )
        if ts.time() != close_time:
            return Fill(symbol=order.symbol, quantity=0, price=market_price)
        qty = self._apply_tif(order, abs(order.quantity), ts, bar_volume)
        qty = qty if order.quantity >= 0 else -qty
        return Fill(symbol=order.symbol, quantity=qty, price=market_price)


class TrailingStopFillModel(BaseFillModel):
    """Trailing stop orders adjust their stop with favorable price moves."""

    @staticmethod
    def _ensure_stop_price(order: Order, market_price: float) -> float:
        base_stop = (
            market_price + order.trail_amount
            if order.quantity > 0
            else market_price - order.trail_amount
        )
        return base_stop if order.stop_price is None else order.stop_price

    @staticmethod
    def _adjust_trailing_stop(order: Order, market_price: float) -> float:
        if order.quantity > 0:
            return min(order.stop_price, market_price + order.trail_amount)
        return max(order.stop_price, market_price - order.trail_amount)

    @staticmethod
    def _triggered(order: Order, market_price: float) -> bool:
        return (
            market_price >= order.stop_price
            if order.quantity > 0
            else market_price <= order.stop_price
        )

    def fill(
        self,
        order: Order,
        market_price: float,
        *,
        ts: Optional[datetime] = None,
        exchange_hours=None,
        bar_volume: Optional[int] = None,
    ) -> Fill:
        if order.trail_amount is None:
            return Fill(symbol=order.symbol, quantity=0, price=market_price)

        order.stop_price = self._ensure_stop_price(order, market_price)
        order.stop_price = self._adjust_trailing_stop(order, market_price)

        if not self._triggered(order, market_price):
            return Fill(symbol=order.symbol, quantity=0, price=market_price)

        qty = self._apply_tif(order, abs(order.quantity), ts, bar_volume)
        qty = qty if order.quantity >= 0 else -qty
        return Fill(symbol=order.symbol, quantity=qty, price=market_price)


class UnifiedFillModel(FillModel):
    """Dispatch to the appropriate fill model by order type.

    This adapter enables a single ``FillModel`` to support multiple
    order types, mirroring how backtest engines route orders to
    different handlers. It preserves the simple IOC/FOK behavior via
    the ``liquidity_cap`` knob on ``BaseFillModel`` derivatives.
    """

    def __init__(
        self, *, liquidity_cap: Optional[int] = None, volume_limit: Optional[float] = None
    ) -> None:
        self._fillers = {
            OrderType.MARKET: MarketFillModel(
                liquidity_cap=liquidity_cap, volume_limit=volume_limit
            ),
            OrderType.LIMIT: LimitFillModel(
                liquidity_cap=liquidity_cap, volume_limit=volume_limit
            ),
            OrderType.STOP: StopMarketFillModel(
                liquidity_cap=liquidity_cap, volume_limit=volume_limit
            ),
            OrderType.STOP_LIMIT: StopLimitFillModel(
                liquidity_cap=liquidity_cap, volume_limit=volume_limit
            ),
            OrderType.MOO: MarketOnOpenFillModel(
                liquidity_cap=liquidity_cap, volume_limit=volume_limit
            ),
            OrderType.MOC: MarketOnCloseFillModel(
                liquidity_cap=liquidity_cap, volume_limit=volume_limit
            ),
            OrderType.TRAILING_STOP: TrailingStopFillModel(
                liquidity_cap=liquidity_cap, volume_limit=volume_limit
            ),
        }

    def fill(
        self,
        order: Order,
        market_price: float,
        *,
        ts: Optional[datetime] = None,
        exchange_hours=None,
        bar_volume: Optional[int] = None,
    ) -> Fill:
        handler = self._fillers.get(order.type)
        if handler is not None:
            return handler.fill(
                order,
                market_price,
                ts=ts,
                exchange_hours=exchange_hours,
                bar_volume=bar_volume,
            )

        return Fill(symbol=order.symbol, quantity=0, price=market_price)
