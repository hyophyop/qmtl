"""Concrete brokerage model implementations and profiles.

This module provides complete brokerage profiles for different brokers,
implementing the full validation and execution pipeline similar to Lean's
brokerage models.
"""

from __future__ import annotations

from datetime import datetime, time
from decimal import Decimal
from typing import Dict, List

from .brokerage_models import (
    AccountType, Currency, IBrokerageModel, ISymbolPropertiesProvider,
    IFeeModel, ISlippageModel, IBuyingPowerModel, ISettlementModel,
    IShortableProvider, IMarginInterestModel, SymbolProperties,
    DefaultSymbolPropertiesProvider, PerShareFeeModel, VolumeShareSlippageModel,
    CashBuyingPowerModel, T2SettlementModel, DefaultShortableProvider,
    DefaultMarginInterestModel, ValidationResult
)
from .execution_modeling import MarketData, OrderSide, OrderType
from .timing_controls import MarketHours, MarketSession


class InteractiveBrokersFeeModel:
    """Interactive Brokers tiered fee model."""
    
    def __init__(self):
        # IB's tiered pricing (simplified)
        self.tiers = [
            (300, Decimal("0.005")),     # First 300 shares: $0.005/share
            (3000, Decimal("0.003")),    # Next 2700 shares: $0.003/share
            (20000, Decimal("0.002")),   # Next 17000 shares: $0.002/share
            (100000, Decimal("0.001")),  # Next 80000 shares: $0.001/share
            (float('inf'), Decimal("0.0005"))  # Over 100k: $0.0005/share
        ]
        self.minimum_fee = Decimal("1.00")
        self.maximum_fee_pct = Decimal("0.01")  # 1% of trade value
    
    def get_order_fee(
        self,
        symbol: str,
        quantity: float,
        price: float,
        order_type: OrderType,
        side: OrderSide
    ) -> Decimal:
        """Calculate IB tiered fee."""
        remaining_qty = quantity
        total_fee = Decimal("0")
        
        for tier_limit, tier_rate in self.tiers:
            if remaining_qty <= 0:
                break
            
            tier_qty = min(remaining_qty, tier_limit)
            total_fee += Decimal(str(tier_qty)) * tier_rate
            remaining_qty -= tier_qty
        
        # Apply minimum
        total_fee = max(total_fee, self.minimum_fee)
        
        # Apply maximum (1% of trade value)
        trade_value = Decimal(str(price)) * Decimal(str(quantity))
        max_fee = trade_value * self.maximum_fee_pct
        total_fee = min(total_fee, max_fee)
        
        return total_fee


class InteractiveBrokersMarginModel:
    """Interactive Brokers margin model with RegT requirements."""
    
    def __init__(self):
        self.initial_margin_req = Decimal("0.50")  # 50% RegT requirement
        self.maintenance_margin_req = Decimal("0.25")  # 25% maintenance
        self.day_trading_buying_power = Decimal("4.0")  # 4:1 leverage
    
    def get_buying_power(
        self,
        portfolio_value: Decimal,
        cash: Decimal,
        positions: Dict[str, float]
    ) -> Decimal:
        """Calculate margin buying power."""
        # Simplified: 2:1 leverage for overnight positions
        return cash * Decimal("2.0")
    
    def get_maximum_order_quantity(
        self,
        symbol: str,
        price: float,
        buying_power: Decimal,
        positions: Dict[str, float]
    ) -> float:
        """Calculate maximum quantity with margin."""
        if price <= 0:
            return 0.0
        
        # Account for initial margin requirement
        effective_price = Decimal(str(price)) * self.initial_margin_req
        return float(buying_power / effective_price)
    
    def get_margin_requirement(
        self,
        symbol: str,
        quantity: float,
        price: float
    ) -> Decimal:
        """Calculate margin requirement."""
        position_value = Decimal(str(price)) * Decimal(str(quantity))
        return position_value * self.initial_margin_req


class InteractiveBrokersShortableProvider:
    """IB shortable provider with realistic constraints."""
    
    def __init__(self):
        # Simplified shortable inventory
        self.shortable_inventory = {
            "AAPL": 100000,
            "MSFT": 100000,
            "GOOGL": 50000,
            "TSLA": 10000,  # Less available
            "SPY": 500000,
            "QQQ": 200000,
        }
        
        self.borrow_rates = {
            "AAPL": Decimal("0.001"),    # 0.1% annual
            "MSFT": Decimal("0.001"),
            "GOOGL": Decimal("0.002"),   # 0.2% annual
            "TSLA": Decimal("0.05"),     # 5% annual (hard to borrow)
            "SPY": Decimal("0.0005"),    # 0.05% annual
            "QQQ": Decimal("0.0005"),
        }
    
    def get_shortable_quantity(
        self,
        symbol: str,
        date: datetime
    ) -> int | None:
        """Get available shortable quantity."""
        return self.shortable_inventory.get(symbol)
    
    def get_borrow_cost(
        self,
        symbol: str,
        quantity: int,
        date: datetime
    ) -> Decimal | None:
        """Get borrow cost rate."""
        return self.borrow_rates.get(symbol)


class InteractiveBrokersBrokerageModel(IBrokerageModel):
    """Complete Interactive Brokers brokerage model."""
    
    def __init__(self, account_type: AccountType = AccountType.MARGIN):
        self._account_type = account_type
        self._name = "Interactive Brokers"
        
        # Initialize all component models
        self._symbol_properties = DefaultSymbolPropertiesProvider()
        self._fee_model = InteractiveBrokersFeeModel()
        self._slippage_model = VolumeShareSlippageModel(price_impact=0.1, volume_limit=0.025)
        
        if account_type == AccountType.MARGIN:
            self._buying_power_model = InteractiveBrokersMarginModel()
        else:
            self._buying_power_model = CashBuyingPowerModel()
        
        self._settlement_model = T2SettlementModel()
        self._shortable_provider = InteractiveBrokersShortableProvider()
        self._margin_interest_model = DefaultMarginInterestModel(Decimal("0.0325"))  # 3.25%
    
    @property
    def name(self) -> str:
        return self._name
    
    @property
    def account_type(self) -> AccountType:
        return self._account_type
    
    @property
    def required_free_buying_power_percent(self) -> Decimal:
        """IB requires 5% free buying power buffer."""
        return Decimal("0.05")
    
    def can_submit_order(
        self,
        symbol: str,
        order_type: OrderType,
        side: OrderSide,
        quantity: float,
        price: float,
        market_data: MarketData,
        timestamp: datetime
    ) -> ValidationResult:
        """Validate order submission."""
        result = ValidationResult(is_valid=True, errors=[], warnings=[])
        
        # Check symbol properties
        props = self._symbol_properties.get_properties(symbol)
        if not props:
            result.add_error(f"Unknown symbol: {symbol}")
            return result
        
        # Validate against symbol properties
        is_valid, msg = props.validate_order(int(quantity), price)
        if not is_valid:
            result.add_error(msg)
        
        # Check market hours
        session = props.market_hours.get_session(timestamp)
        if session == MarketSession.CLOSED:
            result.add_error("Market is closed")
        elif session in [MarketSession.PRE_MARKET, MarketSession.POST_MARKET]:
            # IB allows extended hours but with restrictions
            if order_type != OrderType.LIMIT:
                result.add_error("Only limit orders allowed in extended hours")
            result.add_warning("Trading in extended hours")
        
        # Check short availability for short sales
        if side == OrderSide.SELL:  # Assuming this is a short sale check
            shortable_qty = self._shortable_provider.get_shortable_quantity(symbol, timestamp)
            if shortable_qty is None:
                result.add_error(f"Symbol {symbol} not available for shorting")
            elif shortable_qty < quantity:
                result.add_error(f"Insufficient shortable quantity. Available: {shortable_qty}, Requested: {quantity}")
        
        return result
    
    def can_execute_order(
        self,
        symbol: str,
        order_type: OrderType,
        side: OrderSide,
        quantity: float,
        price: float,
        market_data: MarketData,
        timestamp: datetime
    ) -> ValidationResult:
        """Validate order execution."""
        result = ValidationResult(is_valid=True, errors=[], warnings=[])
        
        # All submission checks apply
        submit_result = self.can_submit_order(symbol, order_type, side, quantity, price, market_data, timestamp)
        result.errors.extend(submit_result.errors)
        result.warnings.extend(submit_result.warnings)
        if not submit_result.is_valid:
            result.is_valid = False
        
        # Additional execution checks
        if order_type == OrderType.MARKET:
            # Market orders execute immediately if market is open
            props = self._symbol_properties.get_properties(symbol)
            if props:
                session = props.market_hours.get_session(timestamp)
                if session == MarketSession.CLOSED:
                    result.add_error("Cannot execute market order when market is closed")
        
        elif order_type == OrderType.LIMIT:
            # Check if limit price is reasonable
            if side == OrderSide.BUY and price > market_data.ask * 1.1:
                result.add_warning("Buy limit price significantly above market")
            elif side == OrderSide.SELL and price < market_data.bid * 0.9:
                result.add_warning("Sell limit price significantly below market")
        
        return result
    
    # Properties for component models
    @property
    def symbol_properties_provider(self) -> ISymbolPropertiesProvider:
        return self._symbol_properties
    
    @property
    def fee_model(self) -> IFeeModel:
        return self._fee_model
    
    @property
    def slippage_model(self) -> ISlippageModel:
        return self._slippage_model
    
    @property
    def buying_power_model(self) -> IBuyingPowerModel:
        return self._buying_power_model
    
    @property
    def settlement_model(self) -> ISettlementModel:
        return self._settlement_model
    
    @property
    def shortable_provider(self) -> IShortableProvider:
        return self._shortable_provider
    
    @property
    def margin_interest_model(self) -> IMarginInterestModel:
        return self._margin_interest_model


class DefaultBrokerageModel(IBrokerageModel):
    """Default/generic brokerage model for testing and simple use cases."""
    
    def __init__(self, account_type: AccountType = AccountType.CASH):
        self._account_type = account_type
        self._name = "Default Brokerage"
        
        # Simple default models
        from .brokerage_models import PercentageFeeModel, NullSlippageModel
        
        self._symbol_properties = DefaultSymbolPropertiesProvider()
        self._fee_model = PercentageFeeModel(Decimal("0.001"), Decimal("1.00"))  # 0.1% with $1 min
        self._slippage_model = NullSlippageModel()
        self._buying_power_model = CashBuyingPowerModel()
        self._settlement_model = T2SettlementModel()
        self._shortable_provider = DefaultShortableProvider()
        self._margin_interest_model = DefaultMarginInterestModel()
    
    @property
    def name(self) -> str:
        return self._name
    
    @property
    def account_type(self) -> AccountType:
        return self._account_type
    
    @property
    def required_free_buying_power_percent(self) -> Decimal:
        return Decimal("0.0")  # No buffer required
    
    def can_submit_order(
        self,
        symbol: str,
        order_type: OrderType,
        side: OrderSide,
        quantity: float,
        price: float,
        market_data: MarketData,
        timestamp: datetime
    ) -> ValidationResult:
        """Basic validation."""
        result = ValidationResult(is_valid=True, errors=[], warnings=[])
        
        if quantity <= 0:
            result.add_error("Quantity must be positive")
        
        if price <= 0:
            result.add_error("Price must be positive")
        
        return result
    
    def can_execute_order(
        self,
        symbol: str,
        order_type: OrderType,
        side: OrderSide,
        quantity: float,
        price: float,
        market_data: MarketData,
        timestamp: datetime
    ) -> ValidationResult:
        """Basic execution validation."""
        return self.can_submit_order(symbol, order_type, side, quantity, price, market_data, timestamp)
    
    # Properties for component models
    @property
    def symbol_properties_provider(self) -> ISymbolPropertiesProvider:
        return self._symbol_properties
    
    @property
    def fee_model(self) -> IFeeModel:
        return self._fee_model
    
    @property
    def slippage_model(self) -> ISlippageModel:
        return self._slippage_model
    
    @property
    def buying_power_model(self) -> IBuyingPowerModel:
        return self._buying_power_model
    
    @property
    def settlement_model(self) -> ISettlementModel:
        return self._settlement_model
    
    @property
    def shortable_provider(self) -> IShortableProvider:
        return self._shortable_provider
    
    @property
    def margin_interest_model(self) -> IMarginInterestModel:
        return self._margin_interest_model


# Brokerage factory for easy instantiation
class BrokerageFactory:
    """Factory for creating brokerage models."""
    
    @staticmethod
    def create_interactive_brokers(account_type: AccountType = AccountType.MARGIN) -> InteractiveBrokersBrokerageModel:
        """Create Interactive Brokers brokerage model."""
        return InteractiveBrokersBrokerageModel(account_type)
    
    @staticmethod
    def create_default(account_type: AccountType = AccountType.CASH) -> DefaultBrokerageModel:
        """Create default brokerage model."""
        return DefaultBrokerageModel(account_type)
    
    @staticmethod
    def get_available_models() -> List[str]:
        """Get list of available brokerage models."""
        return ["interactive_brokers", "default"]