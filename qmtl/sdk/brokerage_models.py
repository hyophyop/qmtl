"""Lean-style brokerage models for QMTL execution framework.

This module implements a comprehensive brokerage modeling system similar to 
QuantConnect's Lean engine, providing realistic trading simulation with:
- Symbol properties (tick size, lot size, multipliers)
- Market hours and calendar management
- Buying power and margin requirements
- Fee, slippage, and settlement models
- Short availability tracking
- Pre-trade validation
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, time, timezone
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional, Protocol, Tuple, Union

from .execution_modeling import MarketData, OrderSide, OrderType
from .timing_controls import MarketHours, MarketSession

logger = logging.getLogger(__name__)


class AccountType(str, Enum):
    """Account types for brokerage models."""
    CASH = "cash"
    MARGIN = "margin"


class Currency(str, Enum):
    """Supported currencies."""
    USD = "USD"
    EUR = "EUR"
    GBP = "GBP"
    JPY = "JPY"
    CAD = "CAD"
    AUD = "AUD"


@dataclass
class SymbolProperties:
    """Properties for a specific symbol/security."""
    
    symbol: str
    tick_size: Decimal  # Minimum price increment
    lot_size: int  # Minimum order quantity
    contract_multiplier: int  # For futures/options
    currency: Currency
    market_hours: MarketHours
    min_price_variation: Decimal
    max_order_quantity: Optional[int] = None
    min_order_value: Optional[Decimal] = None
    
    def round_price(self, price: float) -> Decimal:
        """Round price to valid tick size."""
        price_decimal = Decimal(str(price))
        return (price_decimal / self.tick_size).quantize(Decimal('1')) * self.tick_size
    
    def round_quantity(self, quantity: float) -> int:
        """Round quantity to valid lot size."""
        return int(quantity // self.lot_size) * self.lot_size
    
    def validate_order(self, quantity: int, price: float) -> Tuple[bool, str]:
        """Validate order against symbol properties."""
        if quantity <= 0:
            return False, "Quantity must be positive"
        
        if quantity % self.lot_size != 0:
            return False, f"Quantity must be multiple of lot size {self.lot_size}"
        
        if self.max_order_quantity and quantity > self.max_order_quantity:
            return False, f"Quantity exceeds maximum {self.max_order_quantity}"
        
        rounded_price = self.round_price(price)
        if abs(float(rounded_price) - price) > 1e-6:
            return False, f"Price must be multiple of tick size {self.tick_size}"
        
        order_value = Decimal(str(price)) * quantity
        if self.min_order_value and order_value < self.min_order_value:
            return False, f"Order value below minimum {self.min_order_value}"
        
        return True, "Valid"


class ISymbolPropertiesProvider(Protocol):
    """Interface for providing symbol properties."""
    
    def get_properties(self, symbol: str) -> Optional[SymbolProperties]:
        """Get properties for a symbol."""
        ...
    
    def get_all_symbols(self) -> List[str]:
        """Get all available symbols."""
        ...


class IFeeModel(Protocol):
    """Interface for calculating trading fees."""
    
    def get_order_fee(
        self, 
        symbol: str,
        quantity: float,
        price: float,
        order_type: OrderType,
        side: OrderSide
    ) -> Decimal:
        """Calculate fee for an order."""
        ...


class ISlippageModel(Protocol):
    """Interface for calculating slippage."""
    
    def get_slippage(
        self,
        symbol: str,
        market_data: MarketData,
        order_type: OrderType,
        side: OrderSide,
        quantity: float
    ) -> float:
        """Calculate slippage for an order."""
        ...


class IBuyingPowerModel(Protocol):
    """Interface for buying power calculations."""
    
    def get_buying_power(
        self,
        portfolio_value: Decimal,
        cash: Decimal,
        positions: Dict[str, float]
    ) -> Decimal:
        """Calculate available buying power."""
        ...
    
    def get_maximum_order_quantity(
        self,
        symbol: str,
        price: float,
        buying_power: Decimal,
        positions: Dict[str, float]
    ) -> float:
        """Calculate maximum order quantity possible."""
        ...
    
    def get_margin_requirement(
        self,
        symbol: str,
        quantity: float,
        price: float
    ) -> Decimal:
        """Calculate margin requirement for position."""
        ...


class ISettlementModel(Protocol):
    """Interface for settlement processing."""
    
    def get_settlement_date(
        self,
        symbol: str,
        trade_date: datetime
    ) -> datetime:
        """Get settlement date for a trade."""
        ...
    
    def apply_settlement(
        self,
        cash: Decimal,
        pending_settlements: List[Tuple[datetime, Decimal]]
    ) -> Decimal:
        """Apply settled funds to cash balance."""
        ...


class IShortableProvider(Protocol):
    """Interface for short availability."""
    
    def get_shortable_quantity(
        self,
        symbol: str,
        date: datetime
    ) -> Optional[int]:
        """Get available shares for shorting."""
        ...
    
    def get_borrow_cost(
        self,
        symbol: str,
        quantity: int,
        date: datetime
    ) -> Optional[Decimal]:
        """Get cost to borrow shares."""
        ...


class IMarginInterestModel(Protocol):
    """Interface for margin interest calculations."""
    
    def get_interest_rate(
        self,
        currency: Currency,
        date: datetime
    ) -> Decimal:
        """Get margin interest rate."""
        ...
    
    def calculate_daily_interest(
        self,
        margin_used: Decimal,
        rate: Decimal
    ) -> Decimal:
        """Calculate daily margin interest charge."""
        ...


@dataclass
class ValidationResult:
    """Result of order validation."""
    is_valid: bool
    errors: List[str]
    warnings: List[str]
    
    def add_error(self, message: str) -> None:
        """Add validation error."""
        self.is_valid = False
        self.errors.append(message)
    
    def add_warning(self, message: str) -> None:
        """Add validation warning."""
        self.warnings.append(message)


class IBrokerageModel(ABC):
    """Base interface for brokerage models."""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Brokerage name."""
        ...
    
    @property
    @abstractmethod
    def account_type(self) -> AccountType:
        """Account type."""
        ...
    
    @property
    @abstractmethod
    def required_free_buying_power_percent(self) -> Decimal:
        """Required percentage of buying power to keep free."""
        ...
    
    @abstractmethod
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
        """Validate if order can be submitted."""
        ...
    
    @abstractmethod
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
        """Validate if order can be executed."""
        ...
    
    @property
    @abstractmethod
    def symbol_properties_provider(self) -> ISymbolPropertiesProvider:
        """Symbol properties provider."""
        ...
    
    @property
    @abstractmethod
    def fee_model(self) -> IFeeModel:
        """Fee calculation model."""
        ...
    
    @property
    @abstractmethod
    def slippage_model(self) -> ISlippageModel:
        """Slippage calculation model."""
        ...
    
    @property
    @abstractmethod
    def buying_power_model(self) -> IBuyingPowerModel:
        """Buying power calculation model."""
        ...
    
    @property
    @abstractmethod
    def settlement_model(self) -> ISettlementModel:
        """Settlement processing model."""
        ...
    
    @property
    @abstractmethod
    def shortable_provider(self) -> IShortableProvider:
        """Short availability provider."""
        ...
    
    @property
    @abstractmethod
    def margin_interest_model(self) -> IMarginInterestModel:
        """Margin interest calculation model."""
        ...


# Default implementations

class DefaultSymbolPropertiesProvider:
    """Default implementation of symbol properties provider."""
    
    def __init__(self):
        self._properties: Dict[str, SymbolProperties] = {}
        self._add_default_properties()
    
    def _add_default_properties(self):
        """Add default properties for common symbols."""
        # US Equities
        default_hours = MarketHours(
            pre_market_start=time(4, 0),
            regular_start=time(9, 30),
            regular_end=time(16, 0),
            post_market_end=time(20, 0),
            timezone="US/Eastern"
        )
        
        # Default equity properties
        equity_props = SymbolProperties(
            symbol="EQUITY_DEFAULT",
            tick_size=Decimal("0.01"),
            lot_size=1,
            contract_multiplier=1,
            currency=Currency.USD,
            market_hours=default_hours,
            min_price_variation=Decimal("0.01"),
            min_order_value=Decimal("1.00")
        )
        
        # Common symbols (this would typically come from a database)
        for symbol in ["AAPL", "MSFT", "GOOGL", "TSLA", "SPY", "QQQ"]:
            props = SymbolProperties(
                symbol=symbol,
                tick_size=Decimal("0.01"),
                lot_size=1,
                contract_multiplier=1,
                currency=Currency.USD,
                market_hours=default_hours,
                min_price_variation=Decimal("0.01"),
                min_order_value=Decimal("1.00")
            )
            self._properties[symbol] = props
    
    def get_properties(self, symbol: str) -> Optional[SymbolProperties]:
        """Get properties for a symbol."""
        return self._properties.get(symbol)
    
    def get_all_symbols(self) -> List[str]:
        """Get all available symbols."""
        return list(self._properties.keys())
    
    def add_symbol(self, properties: SymbolProperties) -> None:
        """Add symbol properties."""
        self._properties[properties.symbol] = properties


class PercentageFeeModel:
    """Fee model based on percentage of trade value."""
    
    def __init__(self, rate: Decimal, minimum: Decimal = Decimal("0")):
        self.rate = rate
        self.minimum = minimum
    
    def get_order_fee(
        self,
        symbol: str,
        quantity: float,
        price: float,
        order_type: OrderType,
        side: OrderSide
    ) -> Decimal:
        """Calculate percentage-based fee."""
        trade_value = Decimal(str(price)) * Decimal(str(quantity))
        fee = trade_value * self.rate
        return max(fee, self.minimum)


class FixedFeeModel:
    """Fixed fee per trade model."""
    
    def __init__(self, fee: Decimal):
        self.fee = fee
    
    def get_order_fee(
        self,
        symbol: str,
        quantity: float,
        price: float,
        order_type: OrderType,
        side: OrderSide
    ) -> Decimal:
        """Calculate fixed fee."""
        return self.fee


class PerShareFeeModel:
    """Fee model based on per-share pricing."""
    
    def __init__(self, per_share: Decimal, minimum: Decimal = Decimal("0"), maximum: Optional[Decimal] = None):
        self.per_share = per_share
        self.minimum = minimum
        self.maximum = maximum
    
    def get_order_fee(
        self,
        symbol: str,
        quantity: float,
        price: float,
        order_type: OrderType,
        side: OrderSide
    ) -> Decimal:
        """Calculate per-share fee."""
        fee = Decimal(str(quantity)) * self.per_share
        fee = max(fee, self.minimum)
        if self.maximum:
            fee = min(fee, self.maximum)
        return fee


class NullSlippageModel:
    """No slippage model."""
    
    def get_slippage(
        self,
        symbol: str,
        market_data: MarketData,
        order_type: OrderType,
        side: OrderSide,
        quantity: float
    ) -> float:
        """Return zero slippage."""
        return 0.0


class VolumeShareSlippageModel:
    """Slippage model based on volume share."""
    
    def __init__(self, price_impact: float = 0.1, volume_limit: float = 0.025):
        self.price_impact = price_impact
        self.volume_limit = volume_limit
    
    def get_slippage(
        self,
        symbol: str,
        market_data: MarketData,
        order_type: OrderType,
        side: OrderSide,
        quantity: float
    ) -> float:
        """Calculate volume-based slippage."""
        if market_data.volume <= 0:
            return 0.0
        
        volume_ratio = min(quantity / market_data.volume, self.volume_limit)
        slippage_pct = self.price_impact * (volume_ratio ** 2)
        slippage = market_data.mid_price * slippage_pct
        
        # Apply directional slippage
        return slippage if side == OrderSide.BUY else -slippage


class CashBuyingPowerModel:
    """Cash account buying power model."""
    
    def get_buying_power(
        self,
        portfolio_value: Decimal,
        cash: Decimal,
        positions: Dict[str, float]
    ) -> Decimal:
        """For cash accounts, buying power equals available cash."""
        return cash
    
    def get_maximum_order_quantity(
        self,
        symbol: str,
        price: float,
        buying_power: Decimal,
        positions: Dict[str, float]
    ) -> float:
        """Calculate maximum shares affordable."""
        if price <= 0:
            return 0.0
        return float(buying_power / Decimal(str(price)))
    
    def get_margin_requirement(
        self,
        symbol: str,
        quantity: float,
        price: float
    ) -> Decimal:
        """Cash accounts require full value."""
        return Decimal(str(price)) * Decimal(str(quantity))


class T2SettlementModel:
    """T+2 settlement model for US equities."""
    
    def get_settlement_date(
        self,
        symbol: str,
        trade_date: datetime
    ) -> datetime:
        """Add 2 business days for settlement."""
        # Simplified - in reality would account for holidays
        current = trade_date
        business_days = 0
        
        while business_days < 2:
            current = current.replace(day=current.day + 1)
            if current.weekday() < 5:  # Monday = 0, Friday = 4
                business_days += 1
        
        return current
    
    def apply_settlement(
        self,
        cash: Decimal,
        pending_settlements: List[Tuple[datetime, Decimal]]
    ) -> Decimal:
        """Apply settled funds to cash balance."""
        now = datetime.now(timezone.utc)
        settled_amount = Decimal("0")
        
        for settlement_date, amount in pending_settlements:
            if settlement_date <= now:
                settled_amount += amount
        
        return cash + settled_amount


class DefaultShortableProvider:
    """Default shortable provider - assumes all shares are shortable."""
    
    def get_shortable_quantity(
        self,
        symbol: str,
        date: datetime
    ) -> Optional[int]:
        """Return unlimited shortable quantity."""
        return 1_000_000  # Large default quantity
    
    def get_borrow_cost(
        self,
        symbol: str,
        quantity: int,
        date: datetime
    ) -> Optional[Decimal]:
        """Return minimal borrow cost."""
        return Decimal("0.001")  # 0.1% annual rate


class DefaultMarginInterestModel:
    """Default margin interest model."""
    
    def __init__(self, base_rate: Decimal = Decimal("0.05")):
        self.base_rate = base_rate
    
    def get_interest_rate(
        self,
        currency: Currency,
        date: datetime
    ) -> Decimal:
        """Get margin interest rate."""
        return self.base_rate
    
    def calculate_daily_interest(
        self,
        margin_used: Decimal,
        rate: Decimal
    ) -> Decimal:
        """Calculate daily margin interest charge."""
        return margin_used * rate / Decimal("365")