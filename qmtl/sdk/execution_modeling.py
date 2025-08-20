"""Realistic execution modeling for enhanced backtest accuracy."""

from __future__ import annotations

import logging
import math
from typing import Any, Dict, Optional, Tuple, Union
from dataclasses import dataclass
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


class EnhancedAlphaPerformance:
    """Enhanced performance calculation with realistic execution costs."""
    
    def __init__(self, execution_model: Optional[ExecutionModel] = None):
        """Initialize with optional execution model."""
        self.execution_model = execution_model or ExecutionModel()
        self.execution_history: list[ExecutionFill] = []
    
    def add_execution(self, fill: ExecutionFill) -> None:
        """Add an execution fill to the history."""
        self.execution_history.append(fill)
    
    def calculate_execution_metrics(self) -> Dict[str, float]:
        """Calculate execution quality metrics."""
        if not self.execution_history:
            return {}
        
        total_commission = sum(fill.commission for fill in self.execution_history)
        total_slippage = sum(abs(fill.slippage * fill.quantity) for fill in self.execution_history)
        total_market_impact = sum(fill.market_impact * fill.quantity for fill in self.execution_history)
        total_volume = sum(fill.quantity for fill in self.execution_history)
        
        avg_commission_bps = (total_commission / total_volume) * 10000 if total_volume > 0 else 0
        avg_slippage_bps = (total_slippage / total_volume) * 10000 if total_volume > 0 else 0
        avg_market_impact_bps = (total_market_impact / total_volume) * 10000 if total_volume > 0 else 0
        
        # Execution shortfall analysis
        total_shortfall = sum(fill.execution_shortfall * fill.quantity for fill in self.execution_history)
        avg_shortfall_bps = (total_shortfall / total_volume) * 10000 if total_volume > 0 else 0
        
        return {
            "total_trades": len(self.execution_history),
            "total_volume": total_volume,
            "total_commission": total_commission,
            "total_slippage": total_slippage,
            "total_market_impact": total_market_impact,
            "avg_commission_bps": avg_commission_bps,
            "avg_slippage_bps": avg_slippage_bps,
            "avg_market_impact_bps": avg_market_impact_bps,
            "avg_execution_shortfall_bps": avg_shortfall_bps,
            "total_execution_cost": total_commission + total_slippage + total_market_impact,
        }
    
    def adjust_returns_for_costs(self, raw_returns: list[float]) -> list[float]:
        """Adjust raw returns for realistic execution costs."""
        if not self.execution_history or not raw_returns:
            return raw_returns
        
        # Calculate per-period execution costs
        execution_metrics = self.calculate_execution_metrics()
        avg_cost_per_trade = execution_metrics.get("total_execution_cost", 0) / len(self.execution_history)
        
        # Distribute costs across return periods
        cost_per_period = avg_cost_per_trade / len(raw_returns) if raw_returns else 0
        
        # Adjust returns by subtracting execution costs
        adjusted_returns = []
        for ret in raw_returns:
            # Convert cost to return impact (approximate)
            cost_impact = cost_per_period / 10000.0  # Convert to fraction
            adjusted_return = ret - cost_impact
            adjusted_returns.append(adjusted_return)
        
        return adjusted_returns


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
        volume=volume
    )