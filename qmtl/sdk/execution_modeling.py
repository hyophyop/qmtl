"""Realistic execution modeling for enhanced backtest accuracy."""

from __future__ import annotations

import logging
from typing import Dict, List, Tuple
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class OrderType(str, Enum):
    """Order types for execution modeling."""
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class OrderSide(str, Enum):
    """Order sides."""
    BUY = "buy"
    SELL = "sell"


class TimeInForce(str, Enum):
    """Time-in-force policies."""
    GTC = "gtc"
    IOC = "ioc"
    FOK = "fok"


class OrderStatus(str, Enum):
    """Order lifecycle states."""
    NEW = "new"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELED = "canceled"
    EXPIRED = "expired"


@dataclass
class OpenOrder:
    """Represents an order that may persist across bars."""

    order_id: str
    symbol: str
    side: OrderSide
    quantity: float
    order_type: OrderType
    requested_price: float
    tif: TimeInForce = TimeInForce.GTC
    status: OrderStatus = OrderStatus.NEW
    remaining: float | None = None
    fills: List[ExecutionFill] = field(default_factory=list)
    submitted_time: int = 0

    def __post_init__(self) -> None:
        if self.remaining is None:
            self.remaining = self.quantity


@dataclass
class ExecutionFill:
    """Represents a filled order with realistic execution modeling."""
    
    order_id: str
    symbol: str
    side: OrderSide
    quantity: float
    requested_price: float
    fill_price: float
    fill_time: int  # timestamp
    commission: float
    slippage: float
    market_impact: float
    
    @property
    def total_cost(self) -> float:
        """Total execution cost including commission and slippage."""
        return self.commission + abs(self.slippage * self.quantity)
    
    @property
    def execution_shortfall(self) -> float:
        """Difference between requested and actual execution price."""
        return abs(self.fill_price - self.requested_price)


@dataclass
class MarketData:
    """Market data for execution modeling."""
    
    timestamp: int
    bid: float
    ask: float
    last: float
    volume: float
    
    @property
    def spread(self) -> float:
        """Bid-ask spread."""
        return self.ask - self.bid
    
    @property
    def mid_price(self) -> float:
        """Mid-market price."""
        return (self.bid + self.ask) / 2.0
    
    @property
    def spread_pct(self) -> float:
        """Spread as percentage of mid price."""
        mid = self.mid_price
        return (self.spread / mid) if mid > 0 else 0.0


class ExecutionModel:
    """Models realistic order execution with costs and slippage."""
    
    def __init__(
        self,
        *,
        commission_rate: float = 0.001,  # 0.1% commission
        commission_minimum: float = 1.0,  # Minimum $1 commission
        base_slippage_bps: float = 2.0,  # 2 basis points base slippage
        market_impact_coeff: float = 0.1,  # Market impact coefficient
        latency_ms: int = 100,  # 100ms execution latency
        partial_fill_probability: float = 0.05,  # 5% chance of partial fill
        max_partial_fill: float | None = None,  # cap per-bar fill qty
    ):
        """Initialize execution model with realistic parameters.
        
        Parameters
        ----------
        commission_rate : float
            Commission rate as fraction of trade value.
        commission_minimum : float
            Minimum commission charge.
        base_slippage_bps : float
            Base slippage in basis points.
        market_impact_coeff : float
            Coefficient for market impact calculation.
        latency_ms : int
            Execution latency in milliseconds.
        partial_fill_probability : float
            Probability of partial fills for large orders.
        """
        self.commission_rate = commission_rate
        self.commission_minimum = commission_minimum
        self.base_slippage_bps = base_slippage_bps
        self.market_impact_coeff = market_impact_coeff
        self.latency_ms = latency_ms
        self.partial_fill_probability = partial_fill_probability
        self.max_partial_fill = max_partial_fill
        self.open_orders: Dict[str, OpenOrder] = {}
    
    def calculate_commission(self, trade_value: float) -> float:
        """Calculate commission for a trade."""
        commission = trade_value * self.commission_rate
        return max(commission, self.commission_minimum)
    
    def calculate_slippage(
        self, 
        market_data: MarketData,
        order_type: OrderType,
        side: OrderSide,
        quantity: float
    ) -> float:
        """Calculate slippage based on market conditions and order characteristics."""
        
        # Base slippage in price terms
        base_slippage = market_data.mid_price * (self.base_slippage_bps / 10000.0)
        
        # Market impact based on order size relative to typical volume
        if market_data.volume > 0:
            volume_ratio = quantity / market_data.volume
            market_impact = self.market_impact_coeff * volume_ratio * market_data.mid_price
        else:
            market_impact = 0.0
        
        # Spread cost for market orders
        if order_type == OrderType.MARKET:
            spread_cost = market_data.spread / 2.0
        else:
            spread_cost = 0.0
        
        # Total slippage
        total_slippage = base_slippage + market_impact + spread_cost
        
        # Apply directional slippage (buy orders pay more, sell orders receive less)
        if side == OrderSide.BUY:
            return total_slippage
        else:
            return -total_slippage
    
    def simulate_execution(
        self,
        order_id: str,
        symbol: str,
        side: OrderSide,
        quantity: float,
        order_type: OrderType,
        requested_price: float,
        market_data: MarketData,
        timestamp: int
    ) -> ExecutionFill:
        """Simulate realistic order execution."""
        
        # Calculate execution price based on order type
        if order_type == OrderType.MARKET:
            # Market orders execute at bid/ask
            if side == OrderSide.BUY:
                base_price = market_data.ask
            else:
                base_price = market_data.bid
        else:
            # Limit orders execute at requested price if possible
            base_price = requested_price
        
        # Calculate slippage
        slippage = self.calculate_slippage(market_data, order_type, side, quantity)
        
        # Apply slippage to get final fill price
        fill_price = base_price + slippage
        
        # Calculate commission
        trade_value = quantity * fill_price
        commission = self.calculate_commission(trade_value)
        
        # Add execution latency
        fill_time = timestamp + self.latency_ms
        
        # Calculate market impact
        if market_data.volume > 0:
            volume_ratio = quantity / market_data.volume
            market_impact = self.market_impact_coeff * volume_ratio * market_data.mid_price
        else:
            market_impact = 0.0
        
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
            market_impact=market_impact
        )

    def _price_crossed(self, order: OpenOrder, market_data: MarketData) -> bool:
        """Check if market prices satisfy the order's limit."""
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
    ) -> List[ExecutionFill]:
        """Attempt to fill an order and update its state."""
        fills: List[ExecutionFill] = []
        if not self._price_crossed(order, market_data):
            return fills

        if allow_partial:
            qty = (
                order.remaining
                if self.max_partial_fill is None
                else min(order.remaining, self.max_partial_fill)
            )
        else:
            qty = order.remaining
            if self.max_partial_fill is not None and self.max_partial_fill < qty:
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

        if order.tif == TimeInForce.GTC and order.status in (
            OrderStatus.NEW,
            OrderStatus.PARTIALLY_FILLED,
        ):
            self.open_orders[order.order_id] = order

        return order

    def update_open_orders(
        self, market_data: MarketData, timestamp: int
    ) -> List[ExecutionFill]:
        """Process all outstanding GTC orders with new market data."""
        fills: List[ExecutionFill] = []
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
        market_data: MarketData
    ) -> Tuple[bool, str]:
        """Validate order against market conditions."""
        
        if quantity <= 0:
            return False, "Quantity must be positive"
        
        if price <= 0:
            return False, "Price must be positive"
        
        # Check if limit orders are reasonable relative to market
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
    spread_estimate: float = 0.001  # Default 0.1% spread
) -> MarketData:
    """Create MarketData from OHLCV data with estimated bid/ask."""
    
    # Use close price as reference and estimate bid/ask
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
