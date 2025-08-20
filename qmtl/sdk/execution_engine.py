"""Integrated execution engine that combines brokerage models with execution simulation.

This module provides the complete execution pipeline that:
1. Validates orders using brokerage models
2. Simulates realistic execution with slippage and fees
3. Manages order state and partial fills
4. Handles settlement and margin interest
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional, Tuple

from .brokerage_models import IBrokerageModel, ValidationResult, Currency
from .execution_modeling import (
    ExecutionFill, ExecutionModel, MarketData, OrderSide, OrderType,
    create_market_data_from_ohlcv
)
from .timing_controls import MarketSession

logger = logging.getLogger(__name__)


class OrderStatus(str, Enum):
    """Order status enumeration."""
    PENDING = "pending"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class TimeInForce(str, Enum):
    """Time in force enumeration."""
    GTC = "gtc"  # Good Till Cancelled
    DAY = "day"  # Day order
    IOC = "ioc"  # Immediate Or Cancel
    FOK = "fok"  # Fill Or Kill


@dataclass
class Order:
    """Order representation with full lifecycle management."""
    
    order_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: float
    price: float
    time_in_force: TimeInForce = TimeInForce.GTC
    submitted_time: Optional[datetime] = None
    status: OrderStatus = OrderStatus.PENDING
    filled_quantity: float = 0.0
    remaining_quantity: float = field(init=False)
    avg_fill_price: float = 0.0
    total_commission: Decimal = field(default_factory=lambda: Decimal("0"))
    fills: List[ExecutionFill] = field(default_factory=list)
    rejection_reason: Optional[str] = None
    
    def __post_init__(self):
        """Initialize computed fields."""
        self.remaining_quantity = self.quantity - self.filled_quantity
        if self.submitted_time is None:
            self.submitted_time = datetime.now(timezone.utc)
    
    @property
    def is_complete(self) -> bool:
        """Check if order is completely filled."""
        return self.remaining_quantity <= 0.001  # Allow for small rounding errors
    
    @property
    def fill_percentage(self) -> float:
        """Get percentage of order filled."""
        if self.quantity == 0:
            return 0.0
        return self.filled_quantity / self.quantity
    
    def add_fill(self, fill: ExecutionFill) -> None:
        """Add a fill to this order."""
        self.fills.append(fill)
        self.filled_quantity += fill.quantity
        self.remaining_quantity = self.quantity - self.filled_quantity
        self.total_commission += Decimal(str(fill.commission))
        
        # Update average fill price
        total_filled_value = sum(f.fill_price * f.quantity for f in self.fills)
        self.avg_fill_price = total_filled_value / self.filled_quantity
        
        # Update status
        if self.is_complete:
            self.status = OrderStatus.FILLED
        elif self.filled_quantity > 0:
            self.status = OrderStatus.PARTIALLY_FILLED


@dataclass
class Portfolio:
    """Portfolio state with cash and positions."""
    
    cash: Decimal = field(default_factory=lambda: Decimal("100000"))  # $100k default
    positions: Dict[str, float] = field(default_factory=dict)
    pending_settlements: List[Tuple[datetime, Decimal]] = field(default_factory=list)
    margin_used: Decimal = field(default_factory=lambda: Decimal("0"))
    
    def get_position(self, symbol: str) -> float:
        """Get position size for symbol."""
        return self.positions.get(symbol, 0.0)
    
    def update_position(self, symbol: str, quantity: float) -> None:
        """Update position for symbol."""
        current = self.positions.get(symbol, 0.0)
        new_position = current + quantity
        
        if abs(new_position) < 1e-6:  # Close to zero
            self.positions.pop(symbol, None)
        else:
            self.positions[symbol] = new_position
    
    def apply_trade(self, fill: ExecutionFill) -> None:
        """Apply a trade execution to portfolio."""
        # Update position
        trade_quantity = fill.quantity if fill.side == OrderSide.BUY else -fill.quantity
        self.update_position(fill.symbol, trade_quantity)
        
        # Update cash (subtract cost for buys, add proceeds for sells)
        trade_value = Decimal(str(fill.fill_price * fill.quantity))
        commission = Decimal(str(fill.commission))
        
        if fill.side == OrderSide.BUY:
            self.cash -= (trade_value + commission)
        else:
            self.cash += (trade_value - commission)
    
    def get_total_value(self, market_prices: Dict[str, float]) -> Decimal:
        """Calculate total portfolio value."""
        position_value = Decimal("0")
        for symbol, quantity in self.positions.items():
            if symbol in market_prices:
                position_value += Decimal(str(market_prices[symbol])) * Decimal(str(quantity))
        
        return self.cash + position_value


class EnhancedExecutionEngine:
    """Enhanced execution engine with full brokerage model integration."""
    
    def __init__(self, brokerage_model: IBrokerageModel):
        self.brokerage_model = brokerage_model
        self.orders: Dict[str, Order] = {}
        self.portfolio = Portfolio()
        self.execution_model = ExecutionModel()
        self._next_order_id = 1
        
        logger.info(f"Initialized execution engine with {brokerage_model.name} brokerage model")
    
    def generate_order_id(self) -> str:
        """Generate unique order ID."""
        order_id = f"ORD_{self._next_order_id:06d}"
        self._next_order_id += 1
        return order_id
    
    def submit_order(
        self,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        quantity: float,
        price: float,
        time_in_force: TimeInForce = TimeInForce.GTC,
        market_data: Optional[MarketData] = None,
        timestamp: Optional[datetime] = None
    ) -> Tuple[str, ValidationResult]:
        """Submit an order for execution."""
        
        if timestamp is None:
            timestamp = datetime.now(timezone.utc)
        
        if market_data is None:
            # Create dummy market data if not provided
            market_data = MarketData(
                timestamp=int(timestamp.timestamp()),
                bid=price * 0.999,
                ask=price * 1.001,
                last=price,
                volume=100000
            )
        
        # Generate order ID
        order_id = self.generate_order_id()
        
        # Validate order submission
        validation = self.brokerage_model.can_submit_order(
            symbol, order_type, side, quantity, price, market_data, timestamp
        )
        
        if not validation.is_valid:
            # Create rejected order
            order = Order(
                order_id=order_id,
                symbol=symbol,
                side=side,
                order_type=order_type,
                quantity=quantity,
                price=price,
                time_in_force=time_in_force,
                submitted_time=timestamp,
                status=OrderStatus.REJECTED,
                rejection_reason="; ".join(validation.errors)
            )
            self.orders[order_id] = order
            logger.warning(f"Order {order_id} rejected: {validation.errors}")
            return order_id, validation
        
        # Create and store order
        order = Order(
            order_id=order_id,
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=price,
            time_in_force=time_in_force,
            submitted_time=timestamp,
            status=OrderStatus.PENDING
        )
        self.orders[order_id] = order
        
        # Try immediate execution for market orders or if conditions are met
        should_try_execution = (order_type == OrderType.MARKET or 
                               self._should_execute_immediately(order, market_data, timestamp))
        
        if should_try_execution:
            executed = self._attempt_execution(order, market_data, timestamp)
        else:
            executed = False
            
        # Handle IOC orders that couldn't execute immediately
        if (order.time_in_force == TimeInForce.IOC and 
            (not executed or order.status == OrderStatus.PENDING)):
            order.status = OrderStatus.CANCELLED
            order.rejection_reason = "IOC order could not execute immediately"
        
        logger.info(f"Order {order_id} submitted: {side} {quantity} {symbol} @ {price} ({order_type})")
        return order_id, validation
    
    def _should_execute_immediately(self, order: Order, market_data: MarketData, timestamp: datetime) -> bool:
        """Check if order should execute immediately."""
        if order.order_type == OrderType.MARKET:
            return True
        
        if order.order_type == OrderType.LIMIT:
            if order.side == OrderSide.BUY and order.price >= market_data.ask:
                return True
            elif order.side == OrderSide.SELL and order.price <= market_data.bid:
                return True
        
        return False
    
    def _attempt_execution(self, order: Order, market_data: MarketData, timestamp: datetime) -> bool:
        """Attempt to execute an order."""
        
        # Validate execution
        validation = self.brokerage_model.can_execute_order(
            order.symbol, order.order_type, order.side, 
            order.remaining_quantity, order.price, market_data, timestamp
        )
        
        if not validation.is_valid:
            if order.time_in_force == TimeInForce.IOC or order.time_in_force == TimeInForce.FOK:
                order.status = OrderStatus.CANCELLED
                order.rejection_reason = "Cannot execute: " + "; ".join(validation.errors)
            return False
        
        # Calculate execution quantity
        fill_quantity = self._calculate_fill_quantity(order, market_data)
        
        if fill_quantity <= 0:
            return False
        
        # For FOK orders, must fill completely or not at all
        if order.time_in_force == TimeInForce.FOK and fill_quantity < order.remaining_quantity:
            order.status = OrderStatus.CANCELLED
            order.rejection_reason = "FOK order cannot be filled completely"
            return False
        
        # Simulate execution using ExecutionModel
        fill = self.execution_model.simulate_execution(
            order_id=order.order_id,
            symbol=order.symbol,
            side=order.side,
            quantity=fill_quantity,
            order_type=order.order_type,
            requested_price=order.price,
            market_data=market_data,
            timestamp=int(timestamp.timestamp())
        )
        
        # Apply brokerage-specific adjustments
        fill = self._apply_brokerage_models(fill, market_data)
        
        # Add fill to order
        order.add_fill(fill)
        
        # Apply to portfolio
        self.portfolio.apply_trade(fill)
        
        # Handle IOC orders - cancel remaining quantity
        if order.time_in_force == TimeInForce.IOC and not order.is_complete:
            order.status = OrderStatus.CANCELLED
        
        logger.info(f"Executed {fill_quantity} shares of order {order.order_id} at {fill.fill_price}")
        return True
    
    def _calculate_fill_quantity(self, order: Order, market_data: MarketData) -> float:
        """Calculate how much of the order can be filled."""
        # For now, assume we can fill the entire remaining quantity
        # In a more sophisticated model, this would consider:
        # - Available volume
        # - Order book depth  
        # - Liquidity constraints
        
        max_quantity = order.remaining_quantity
        
        # Apply volume limits if available
        if market_data.volume > 0:
            # Don't consume more than 25% of bar volume (similar to Lean's default)
            volume_limit = market_data.volume * 0.25
            max_quantity = min(max_quantity, volume_limit)
        
        return max_quantity
    
    def _apply_brokerage_models(self, fill: ExecutionFill, market_data: MarketData) -> ExecutionFill:
        """Apply brokerage-specific models to the fill."""
        
        # Apply slippage model
        slippage = self.brokerage_model.slippage_model.get_slippage(
            fill.symbol, market_data, OrderType.MARKET, fill.side, fill.quantity
        )
        
        # Apply fee model
        commission = float(self.brokerage_model.fee_model.get_order_fee(
            fill.symbol, fill.quantity, fill.fill_price, OrderType.MARKET, fill.side
        ))
        
        # Create new fill with brokerage adjustments
        adjusted_fill = ExecutionFill(
            order_id=fill.order_id,
            symbol=fill.symbol,
            side=fill.side,
            quantity=fill.quantity,
            requested_price=fill.requested_price,
            fill_price=fill.fill_price + slippage,
            fill_time=fill.fill_time,
            commission=commission,
            slippage=slippage,
            market_impact=fill.market_impact
        )
        
        return adjusted_fill
    
    def update_market_data(self, symbol: str, market_data: MarketData, timestamp: Optional[datetime] = None) -> None:
        """Update market data and check for order executions."""
        if timestamp is None:
            timestamp = datetime.now(timezone.utc)
        
        # Check all pending orders for this symbol
        pending_orders = [
            order for order in self.orders.values()
            if (order.symbol == symbol and 
                order.status in [OrderStatus.PENDING, OrderStatus.PARTIALLY_FILLED] and
                not order.is_complete)
        ]
        
        for order in pending_orders:
            # Check if order should execute
            if self._should_execute_immediately(order, market_data, timestamp):
                self._attempt_execution(order, market_data, timestamp)
            
            # Handle day orders that expire
            if (order.time_in_force == TimeInForce.DAY and 
                timestamp.date() > order.submitted_time.date()):
                order.status = OrderStatus.CANCELLED
                order.rejection_reason = "Day order expired"
    
    def cancel_order(self, order_id: str) -> bool:
        """Cancel a pending order."""
        if order_id not in self.orders:
            return False
        
        order = self.orders[order_id]
        if order.status in [OrderStatus.PENDING, OrderStatus.PARTIALLY_FILLED]:
            order.status = OrderStatus.CANCELLED
            logger.info(f"Order {order_id} cancelled")
            return True
        
        return False
    
    def get_order(self, order_id: str) -> Optional[Order]:
        """Get order by ID."""
        return self.orders.get(order_id)
    
    def get_orders(self, symbol: Optional[str] = None, status: Optional[OrderStatus] = None) -> List[Order]:
        """Get orders with optional filtering."""
        orders = list(self.orders.values())
        
        if symbol:
            orders = [o for o in orders if o.symbol == symbol]
        
        if status:
            orders = [o for o in orders if o.status == status]
        
        return orders
    
    def get_portfolio_summary(self, market_prices: Dict[str, float]) -> Dict:
        """Get portfolio summary."""
        total_value = self.portfolio.get_total_value(market_prices)
        
        return {
            "cash": float(self.portfolio.cash),
            "positions": dict(self.portfolio.positions),
            "total_value": float(total_value),
            "margin_used": float(self.portfolio.margin_used),
            "buying_power": float(self.brokerage_model.buying_power_model.get_buying_power(
                total_value, self.portfolio.cash, self.portfolio.positions
            ))
        }
    
    def apply_settlement(self, timestamp: Optional[datetime] = None) -> None:
        """Apply settlement to pending trades."""
        if timestamp is None:
            timestamp = datetime.now(timezone.utc)
        
        # Apply settlement model
        settled_cash = self.brokerage_model.settlement_model.apply_settlement(
            self.portfolio.cash, self.portfolio.pending_settlements
        )
        
        # Remove settled items
        self.portfolio.pending_settlements = [
            (date, amount) for date, amount in self.portfolio.pending_settlements
            if date > timestamp
        ]
        
        self.portfolio.cash = settled_cash
    
    def apply_margin_interest(self, timestamp: Optional[datetime] = None) -> None:
        """Apply daily margin interest charges."""
        if timestamp is None:
            timestamp = datetime.now(timezone.utc)
        
        if self.portfolio.margin_used > 0:
            rate = self.brokerage_model.margin_interest_model.get_interest_rate(
                Currency.USD, timestamp
            )
            
            daily_interest = self.brokerage_model.margin_interest_model.calculate_daily_interest(
                self.portfolio.margin_used, rate
            )
            
            self.portfolio.cash -= daily_interest
            logger.debug(f"Applied margin interest: {daily_interest}")