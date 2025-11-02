"""Stateful execution engine built on top of reusable primitives."""

from __future__ import annotations

import logging
from typing import Tuple

from .helpers import (
    apply_latency,
    calculate_commission as commission_helper,
    calculate_market_impact,
    calculate_slippage as slippage_helper,
    determine_fill_quantity,
)
from .models import (
    ExecutionFill,
    MarketData,
    OpenOrder,
    OrderSide,
    OrderStatus,
    OrderType,
    TimeInForce,
)

__all__ = ["ExecutionModel", "create_market_data_from_ohlcv"]

logger = logging.getLogger(__name__)


class ExecutionModel:
    """Models realistic order execution with costs and slippage."""

    def __init__(
        self,
        *,
        commission_rate: float = 0.001,
        commission_minimum: float = 1.0,
        base_slippage_bps: float = 2.0,
        market_impact_coeff: float = 0.1,
        latency_ms: int = 100,
        partial_fill_probability: float = 0.05,
        max_partial_fill: float | None = None,
    ):
        self.commission_rate = commission_rate
        self.commission_minimum = commission_minimum
        self.base_slippage_bps = base_slippage_bps
        self.market_impact_coeff = market_impact_coeff
        self.latency_ms = latency_ms
        self.partial_fill_probability = partial_fill_probability
        self.max_partial_fill = max_partial_fill
        self.open_orders: dict[str, OpenOrder] = {}

    # ------------------------------------------------------------------
    # Cost helpers
    def calculate_commission(self, trade_value: float) -> float:
        """Calculate commission for a trade using the configured policy."""

        return commission_helper(trade_value, self.commission_rate, self.commission_minimum)

    def calculate_slippage(
        self,
        market_data: MarketData,
        order_type: OrderType,
        side: OrderSide,
        quantity: float,
    ) -> float:
        """Directional slippage given the current configuration."""

        return slippage_helper(
            market_data,
            order_type,
            side,
            quantity,
            base_slippage_bps=self.base_slippage_bps,
            market_impact_coeff=self.market_impact_coeff,
        )

    # ------------------------------------------------------------------
    # Execution flow
    def simulate_execution(
        self,
        order_id: str,
        symbol: str,
        side: OrderSide,
        quantity: float,
        order_type: OrderType,
        requested_price: float,
        market_data: MarketData,
        timestamp: int,
    ) -> ExecutionFill:
        """Simulate realistic order execution for a single fill."""

        if order_type == OrderType.MARKET:
            base_price = market_data.ask if side == OrderSide.BUY else market_data.bid
        else:
            base_price = requested_price

        slippage = self.calculate_slippage(market_data, order_type, side, quantity)
        fill_price = base_price + slippage

        trade_value = quantity * fill_price
        commission = self.calculate_commission(trade_value)

        fill_time = apply_latency(timestamp, self.latency_ms)
        market_impact = calculate_market_impact(quantity, market_data, self.market_impact_coeff)

        return ExecutionFill(
            order_id=order_id,
            symbol=symbol,
            side=side,
            quantity=quantity,
            requested_price=requested_price,
            fill_price=fill_price,
            fill_time=fill_time,
            commission=commission,
            slippage=slippage,
            market_impact=market_impact,
        )

    def _price_crossed(self, order: OpenOrder, market_data: MarketData) -> bool:
        """Check if market prices satisfy the order's limit conditions."""

        if order.order_type == OrderType.MARKET:
            return True
        if order.side == OrderSide.BUY:
            return market_data.ask <= order.requested_price
        return market_data.bid >= order.requested_price

    def _process_fill(
        self,
        order: OpenOrder,
        market_data: MarketData,
        timestamp: int,
        *,
        allow_partial: bool = True,
    ) -> list[ExecutionFill]:
        """Attempt to fill an order and update its state."""

        fills: list[ExecutionFill] = []
        if not self._price_crossed(order, market_data):
            return fills

        qty = determine_fill_quantity(
            order.remaining,
            allow_partial=allow_partial,
            max_partial_fill=self.max_partial_fill,
        )
        if qty in (None, 0.0):
            return fills

        fill = self.simulate_execution(
            order.order_id,
            order.symbol,
            order.side,
            qty,
            order.order_type,
            order.requested_price,
            market_data,
            timestamp,
        )

        order.fills.append(fill)
        order.remaining -= qty
        if order.remaining <= 0:
            order.status = OrderStatus.FILLED
        else:
            order.status = OrderStatus.PARTIALLY_FILLED
        fills.append(fill)
        return fills

    def submit_order(
        self,
        order_id: str,
        symbol: str,
        side: OrderSide,
        quantity: float,
        order_type: OrderType,
        requested_price: float,
        tif: TimeInForce,
        market_data: MarketData,
        timestamp: int,
    ) -> OpenOrder:
        """Submit a new order and process immediate fills based on TIF."""

        order = OpenOrder(
            order_id=order_id,
            symbol=symbol,
            side=side,
            quantity=quantity,
            order_type=order_type,
            requested_price=requested_price,
            tif=tif,
            submitted_time=timestamp,
        )

        allow_partial = tif != TimeInForce.FOK
        self._process_fill(order, market_data, timestamp, allow_partial=allow_partial)

        if tif == TimeInForce.IOC and order.remaining > 0:
            order.status = OrderStatus.EXPIRED
        elif tif == TimeInForce.FOK and order.remaining > 0:
            order.status = OrderStatus.EXPIRED
            order.fills.clear()
            order.remaining = quantity

        if order.tif == TimeInForce.GTC and order.status in {
            OrderStatus.NEW,
            OrderStatus.PARTIALLY_FILLED,
        }:
            self.open_orders[order.order_id] = order

        return order

    def update_open_orders(self, market_data: MarketData, timestamp: int) -> list[ExecutionFill]:
        """Process all outstanding GTC orders with new market data."""

        fills: list[ExecutionFill] = []
        for order_id in list(self.open_orders.keys()):
            order = self.open_orders[order_id]
            fills.extend(self._process_fill(order, market_data, timestamp))
            if order.status == OrderStatus.FILLED:
                del self.open_orders[order_id]
        return fills

    def validate_order(
        self,
        side: OrderSide,
        quantity: float,
        price: float,
        market_data: MarketData,
    ) -> Tuple[bool, str]:
        """Validate order parameters against simple market sanity checks."""

        if quantity <= 0:
            return False, "Quantity must be positive"

        if price <= 0:
            return False, "Price must be positive"

        if side == OrderSide.BUY and price > market_data.ask * 1.1:
            return False, "Buy limit price too far above market"

        if side == OrderSide.SELL and price < market_data.bid * 0.9:
            return False, "Sell limit price too far below market"

        return True, "Valid"


def create_market_data_from_ohlcv(
    timestamp: int,
    open_price: float,
    high: float,
    low: float,
    close: float,
    volume: float,
    spread_estimate: float = 0.001,
) -> MarketData:
    """Create :class:`MarketData` from OHLCV data with an estimated spread."""

    half_spread = close * spread_estimate / 2.0
    bid = close - half_spread
    ask = close + half_spread

    return MarketData(
        timestamp=timestamp,
        bid=bid,
        ask=ask,
        last=close,
        volume=volume,
    )
