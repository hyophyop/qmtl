"""Realistic execution modeling for enhanced backtest accuracy."""

from __future__ import annotations

import logging
from typing import Tuple, Optional, Protocol
from dataclasses import dataclass
from enum import Enum
from decimal import Decimal
from abc import ABC, abstractmethod

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
    """Time in force options."""
    GTC = "gtc"  # Good Till Cancelled
    DAY = "day"  # Day order
    IOC = "ioc"  # Immediate Or Cancel
    FOK = "fok"  # Fill Or Kill


class AccountType(str, Enum):
    """Account types for execution modeling."""
    CASH = "cash"
    MARGIN = "margin"


@dataclass
class SymbolProperties:
    """Properties for a specific symbol/security."""
    
    symbol: str
    tick_size: Decimal  # Minimum price increment
    lot_size: int = 1  # Minimum quantity increment
    contract_multiplier: int = 1  # Multiplier for derivatives
    margin_requirement: Decimal = Decimal("0.5")  # Initial margin requirement
    
    def round_price(self, price: float) -> Decimal:
        """Round price to valid tick size."""
        price_decimal = Decimal(str(price))
        return (price_decimal / self.tick_size).quantize(Decimal('1')) * self.tick_size
    
    def round_quantity(self, quantity: float) -> int:
        """Round quantity to valid lot size."""
        return int(quantity // self.lot_size) * self.lot_size


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
    time_in_force: TimeInForce = TimeInForce.GTC
    
    @property
    def total_cost(self) -> float:
        """Total execution cost including commission and slippage."""
        return self.commission + abs(self.slippage * self.quantity)
    
    @property
    def execution_shortfall(self) -> float:
        """Difference between requested and actual execution price."""
        return abs(self.fill_price - self.requested_price)


@dataclass 
class ValidationResult:
    """Result of order validation."""
    
    is_valid: bool
    message: str
    adjusted_quantity: Optional[float] = None
    adjusted_price: Optional[float] = None


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


class IFeeModel(Protocol):
    """Interface for fee calculation models."""
    
    def calculate_fee(self, symbol: str, quantity: float, price: float) -> float:
        """Calculate trading fee for an order."""
        ...


class ISlippageModel(Protocol):
    """Interface for slippage calculation models."""
    
    def calculate_slippage(self, market_data: MarketData, side: OrderSide, quantity: float) -> float:
        """Calculate slippage for an order."""
        ...


class IBuyingPowerModel(Protocol):
    """Interface for buying power calculation models."""
    
    def get_buying_power(self, cash: float, positions: dict) -> float:
        """Calculate available buying power."""
        ...


class PercentageFeeModel:
    """Fee model based on percentage of trade value."""
    
    def __init__(self, commission_rate: float = 0.001, minimum_fee: float = 1.0):
        self.commission_rate = commission_rate
        self.minimum_fee = minimum_fee
    
    def calculate_fee(self, symbol: str, quantity: float, price: float) -> float:
        trade_value = abs(quantity * price)
        return max(trade_value * self.commission_rate, self.minimum_fee)


class VolumeShareSlippageModel:
    """Slippage model based on order size relative to market volume."""
    
    def __init__(self, price_impact_coefficient: float = 0.1, max_volume_share: float = 0.025):
        self.price_impact_coefficient = price_impact_coefficient
        self.max_volume_share = max_volume_share
    
    def calculate_slippage(self, market_data: MarketData, side: OrderSide, quantity: float) -> float:
        if market_data.volume <= 0:
            return 0.0
        
        # Calculate volume share (capped at max_volume_share)
        volume_share = min(quantity / market_data.volume, self.max_volume_share)
        
        # Apply Kissell & Glantz formula: Price Impact = coeff * (volume_share^0.6)
        price_impact = self.price_impact_coefficient * (volume_share ** 0.6) * market_data.mid_price
        
        # Apply directionally - buy orders pay more, sell orders receive less
        return price_impact if side == OrderSide.BUY else -price_impact


class CashBuyingPowerModel:
    """Cash account buying power model - full payment required."""
    
    def get_buying_power(self, cash: float, positions: dict) -> float:
        return max(0.0, cash)


class MarginBuyingPowerModel:
    """Margin account buying power model with leverage."""
    
    def __init__(self, leverage: float = 2.0, maintenance_margin: float = 0.25):
        self.leverage = leverage
        self.maintenance_margin = maintenance_margin
    
    def get_buying_power(self, cash: float, positions: dict) -> float:
        # Simplified calculation: cash * leverage
        # In reality would need to consider existing positions and margin requirements
        return max(0.0, cash * self.leverage)
class ExecutionModel:
    """Enhanced execution model with configurable fee, slippage, and buying power models."""
    
    def __init__(
        self,
        *,
        fee_model: Optional[IFeeModel] = None,
        slippage_model: Optional[ISlippageModel] = None,
        buying_power_model: Optional[IBuyingPowerModel] = None,
        symbol_properties: Optional[dict] = None,
        account_type: AccountType = AccountType.CASH,
        # Legacy parameters for backward compatibility
        commission_rate: float = 0.001,
        commission_minimum: float = 1.0,
        base_slippage_bps: float = 2.0,
        market_impact_coeff: float = 0.1,
        latency_ms: int = 100,
        partial_fill_probability: float = 0.05,
    ):
        """Initialize execution model with realistic parameters.
        
        Parameters
        ----------
        fee_model : IFeeModel, optional
            Custom fee model. If None, uses PercentageFeeModel with legacy parameters.
        slippage_model : ISlippageModel, optional
            Custom slippage model. If None, uses legacy calculation.
        buying_power_model : IBuyingPowerModel, optional
            Custom buying power model. If None, uses CashBuyingPowerModel.
        symbol_properties : dict, optional
            Dictionary mapping symbols to SymbolProperties.
        account_type : AccountType
            Type of trading account.
        """
        self.fee_model = fee_model or PercentageFeeModel(commission_rate, commission_minimum)
        self.slippage_model = slippage_model or VolumeShareSlippageModel(market_impact_coeff)
        self.buying_power_model = buying_power_model or (
            MarginBuyingPowerModel() if account_type == AccountType.MARGIN else CashBuyingPowerModel()
        )
        self.symbol_properties = symbol_properties or {}
        self.account_type = account_type
        
        # Legacy parameters for backward compatibility
        self.commission_rate = commission_rate
        self.commission_minimum = commission_minimum
        self.base_slippage_bps = base_slippage_bps
        self.market_impact_coeff = market_impact_coeff
        self.latency_ms = latency_ms
        self.partial_fill_probability = partial_fill_probability
    
    def calculate_commission(self, symbol: str, quantity: float, price: float) -> float:
        """Calculate commission for a trade using the configured fee model."""
        return self.fee_model.calculate_fee(symbol, quantity, price)
    
    def get_symbol_properties(self, symbol: str) -> SymbolProperties:
        """Get symbol properties, using defaults if not configured."""
        if symbol in self.symbol_properties:
            return self.symbol_properties[symbol]
        
        # Default properties
        return SymbolProperties(
            symbol=symbol,
            tick_size=Decimal("0.01"),
            lot_size=1,
            contract_multiplier=1,
            margin_requirement=Decimal("0.5")
        )
    
    def validate_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        price: float,
        order_type: OrderType,
        market_data: MarketData,
        cash: float = float('inf'),
        positions: Optional[dict] = None
    ) -> ValidationResult:
        """Enhanced order validation with symbol properties and buying power checks."""
        positions = positions or {}
        
        if quantity <= 0:
            return ValidationResult(False, "Quantity must be positive")
        
        if price <= 0:
            return ValidationResult(False, "Price must be positive")
        
        # Get symbol properties and validate
        props = self.get_symbol_properties(symbol)
        
        # Round to valid tick size and lot size
        rounded_price = float(props.round_price(price))
        rounded_quantity = props.round_quantity(quantity)
        
        if rounded_quantity == 0:
            return ValidationResult(False, f"Quantity {quantity} below minimum lot size {props.lot_size}")
        
        # Check buying power
        required_capital = rounded_quantity * rounded_price
        if side == OrderSide.BUY:
            buying_power = self.buying_power_model.get_buying_power(cash, positions)
            if required_capital > buying_power:
                return ValidationResult(
                    False, 
                    f"Insufficient buying power: need ${required_capital:.2f}, have ${buying_power:.2f}"
                )
        
        # Market condition checks for limit orders
        if order_type == OrderType.LIMIT:
            if side == OrderSide.BUY and rounded_price > market_data.ask * 1.1:
                return ValidationResult(False, "Buy limit price too far above market")
            if side == OrderSide.SELL and rounded_price < market_data.bid * 0.9:
                return ValidationResult(False, "Sell limit price too far below market")
        
        # Return valid with any adjustments
        if rounded_price != price or rounded_quantity != quantity:
            return ValidationResult(
                True, 
                "Valid with adjustments", 
                adjusted_quantity=float(rounded_quantity),
                adjusted_price=rounded_price
            )
        
        return ValidationResult(True, "Valid")
    
    def calculate_slippage(
        self, 
        market_data: MarketData,
        order_type: OrderType,
        side: OrderSide,
        quantity: float
    ) -> float:
        """Calculate slippage using configured slippage model or legacy calculation."""
        
        # Use new slippage model if available
        if hasattr(self.slippage_model, 'calculate_slippage'):
            slippage = self.slippage_model.calculate_slippage(market_data, side, quantity)
        else:
            # Legacy calculation for backward compatibility
            slippage = self._calculate_legacy_slippage(market_data, order_type, side, quantity)
        
        return slippage
    
    def _calculate_legacy_slippage(
        self, 
        market_data: MarketData,
        order_type: OrderType,
        side: OrderSide,
        quantity: float
    ) -> float:
        """Legacy slippage calculation for backward compatibility."""
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
        timestamp: int,
        time_in_force: TimeInForce = TimeInForce.GTC
    ) -> ExecutionFill:
        """Simulate realistic order execution with enhanced features."""
        
        # Get symbol properties for price/quantity rounding
        props = self.get_symbol_properties(symbol)
        rounded_price = float(props.round_price(requested_price))
        rounded_quantity = props.round_quantity(quantity)
        
        # Calculate execution price based on order type
        if order_type == OrderType.MARKET:
            # Market orders execute at bid/ask
            if side == OrderSide.BUY:
                base_price = market_data.ask
            else:
                base_price = market_data.bid
        else:
            # Limit orders execute at requested price if possible
            base_price = rounded_price
        
        # Calculate slippage
        slippage = self.calculate_slippage(market_data, order_type, side, rounded_quantity)
        
        # Apply slippage to get final fill price
        fill_price = base_price + slippage
        
        # Round fill price to tick size
        fill_price = float(props.round_price(fill_price))
        
        # Calculate commission
        commission = self.calculate_commission(symbol, rounded_quantity, fill_price)
        
        # Add execution latency
        fill_time = timestamp + self.latency_ms
        
        # Calculate market impact
        if market_data.volume > 0:
            volume_ratio = rounded_quantity / market_data.volume
            market_impact = self.market_impact_coeff * volume_ratio * market_data.mid_price
        else:
            market_impact = 0.0
        
        return ExecutionFill(
            order_id=order_id,
            symbol=symbol,
            side=side,
            quantity=rounded_quantity,
            requested_price=rounded_price,
            fill_price=fill_price,
            fill_time=fill_time,
            commission=commission,
            slippage=slippage,
            market_impact=market_impact,
            time_in_force=time_in_force
        )
    
    def validate_order_legacy(
        self,
        side: OrderSide,
        quantity: float,
        price: float,
        market_data: MarketData
    ) -> Tuple[bool, str]:
        """Legacy validate_order method for backward compatibility."""
        result = self.validate_order("UNKNOWN", side, quantity, price, OrderType.LIMIT, market_data)
        return result.is_valid, result.message


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


class InteractiveBrokersFeeModel:
    """Interactive Brokers tiered commission structure."""
    
    def __init__(self):
        # IB Tiered: $0.005/share for first 300, decreasing with volume
        self.tiers = [
            (300, 0.005),      # First 300 shares
            (3000, 0.003),     # Next 2700 shares  
            (20000, 0.002),    # Next 17000 shares
            (float('inf'), 0.001)  # Above 20000 shares
        ]
        self.minimum_fee = 1.0
        self.maximum_rate = 0.01  # 1% maximum
    
    def calculate_fee(self, symbol: str, quantity: float, price: float) -> float:
        total_fee = 0.0
        remaining_qty = abs(quantity)
        
        for tier_limit, rate in self.tiers:
            if remaining_qty <= 0:
                break
                
            qty_in_tier = min(remaining_qty, tier_limit)
            total_fee += qty_in_tier * rate
            remaining_qty -= qty_in_tier
        
        # Apply minimum and maximum constraints
        trade_value = abs(quantity * price)
        max_fee = trade_value * self.maximum_rate
        
        return max(min(total_fee, max_fee), self.minimum_fee)


class BrokerageFactory:
    """Factory for creating pre-configured brokerage models."""
    
    @staticmethod
    def create_interactive_brokers() -> ExecutionModel:
        """Create Interactive Brokers execution model."""
        from decimal import Decimal
        
        # Default symbol properties for common symbols
        symbol_props = {
            "AAPL": SymbolProperties("AAPL", Decimal("0.01"), 1, 1, Decimal("0.30")),
            "TSLA": SymbolProperties("TSLA", Decimal("0.01"), 1, 1, Decimal("0.40")),
            "SPY": SymbolProperties("SPY", Decimal("0.01"), 1, 1, Decimal("0.25")),
        }
        
        return ExecutionModel(
            fee_model=InteractiveBrokersFeeModel(),
            slippage_model=VolumeShareSlippageModel(price_impact_coefficient=0.1, max_volume_share=0.025),
            buying_power_model=MarginBuyingPowerModel(leverage=2.0, maintenance_margin=0.25),
            symbol_properties=symbol_props,
            account_type=AccountType.MARGIN,
            latency_ms=50,  # Lower latency for IB
        )
    
    @staticmethod  
    def create_simple_cash_model() -> ExecutionModel:
        """Create simple cash account model for testing."""
        return ExecutionModel(
            fee_model=PercentageFeeModel(commission_rate=0.001, minimum_fee=1.0),
            slippage_model=VolumeShareSlippageModel(price_impact_coefficient=0.05, max_volume_share=0.01),
            buying_power_model=CashBuyingPowerModel(),
            account_type=AccountType.CASH,
            latency_ms=100,
        )
