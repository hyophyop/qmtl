# Enhanced Execution Modeling in QMTL

This document describes the enhanced execution modeling capabilities that build upon QMTL's existing framework to provide realistic brokerage simulation.

## Overview

The enhanced execution modeling system extends QMTL's existing `ExecutionModel` class with:
- Symbol-specific properties (tick size, lot size, contract multipliers)
- Configurable fee, slippage, and buying power models  
- Pre-configured brokerage profiles (Interactive Brokers, simple cash)
- Integration with existing risk management and market hours functionality

## Key Components

### ExecutionModel (Enhanced)

The existing `ExecutionModel` class has been enhanced with:

```python
from qmtl.sdk import ExecutionModel, AccountType

model = ExecutionModel(
    fee_model=custom_fee_model,
    slippage_model=custom_slippage_model,
    buying_power_model=custom_buying_power_model,
    symbol_properties=symbol_props,
    account_type=AccountType.MARGIN
)
```

### Symbol Properties

Define symbol-specific trading constraints:

```python
from decimal import Decimal
from qmtl.sdk import SymbolProperties

props = SymbolProperties(
    symbol="AAPL",
    tick_size=Decimal("0.01"),  # Minimum price increment
    lot_size=1,                 # Minimum quantity increment  
    contract_multiplier=1,      # For derivatives
    margin_requirement=Decimal("0.30")  # Initial margin requirement
)

# Automatic rounding
rounded_price = props.round_price(100.234)  # -> 100.23
rounded_qty = props.round_quantity(150)     # -> 150 (for lot_size=1)
```

### Fee Models

Multiple fee calculation approaches:

```python
from qmtl.sdk import PercentageFeeModel, InteractiveBrokersFeeModel

# Simple percentage-based fees
percentage_model = PercentageFeeModel(
    commission_rate=0.001,  # 0.1%
    minimum_fee=1.0
)

# Interactive Brokers tiered structure
ib_model = InteractiveBrokersFeeModel()
# $0.005/share for first 300, decreasing with volume
```

### Slippage Models

Realistic price impact simulation:

```python
from qmtl.sdk import VolumeShareSlippageModel

slippage_model = VolumeShareSlippageModel(
    price_impact_coefficient=0.1,
    max_volume_share=0.025  # Cap at 2.5% of volume
)
```

### Buying Power Models

Account-specific constraints:

```python
from qmtl.sdk import CashBuyingPowerModel, MarginBuyingPowerModel

# Cash account - full payment required
cash_model = CashBuyingPowerModel()

# Margin account with leverage
margin_model = MarginBuyingPowerModel(
    leverage=2.0,
    maintenance_margin=0.25
)
```

## BrokerageFactory

Pre-configured execution models for common brokerages:

```python
from qmtl.sdk import BrokerageFactory

# Interactive Brokers model with realistic settings
ib_model = BrokerageFactory.create_interactive_brokers()

# Simple cash model for testing
cash_model = BrokerageFactory.create_simple_cash_model()
```

## Integration with Existing Framework

### Risk Management

Works seamlessly with existing `RiskManager`:

```python
from qmtl.sdk import RiskManager, PositionInfo

risk_manager = RiskManager(
    max_leverage=2.0,
    position_size_limit_pct=0.08
)

# Validate position size before order submission
is_valid, violation, adjusted_qty = risk_manager.validate_position_size(
    symbol="AAPL",
    proposed_quantity=1000,
    current_price=150.0,
    portfolio_value=100000.0,
    current_positions={}
)
```

### Market Hours

Uses existing `MarketHours` and `MarketSession` from timing controls:

```python
from qmtl.sdk import MarketHours, MarketSession
from datetime import time

market_hours = MarketHours(
    pre_market_start=time(4, 0),
    regular_start=time(9, 30),
    regular_end=time(16, 0),
    post_market_end=time(20, 0)
)
```

### Order Validation and Execution

Enhanced validation with automatic adjustments:

```python
from qmtl.sdk import OrderType, OrderSide, create_market_data_from_ohlcv

# Create market data
market_data = create_market_data_from_ohlcv(
    timestamp=1640995200,
    open_price=150.0,
    high=155.0,
    low=148.0,
    close=152.0,
    volume=1000000
)

# Validate order with automatic adjustments
validation = model.validate_order(
    symbol="AAPL",
    side=OrderSide.BUY,
    quantity=100.5,  # Will be rounded to lot size
    price=151.234,   # Will be rounded to tick size
    order_type=OrderType.LIMIT,
    market_data=market_data,
    cash=20000.0
)

if validation.is_valid:
    # Execute with realistic simulation
    fill = model.simulate_execution(
        order_id="ORDER001",
        symbol="AAPL",
        side=OrderSide.BUY,
        quantity=validation.adjusted_quantity or 100,
        order_type=OrderType.MARKET,
        requested_price=validation.adjusted_price or 151.23,
        market_data=market_data,
        timestamp=1640995200000
    )
```

## Example Usage

Complete example showing all features:

```python
from qmtl.sdk import (
    BrokerageFactory, OrderType, OrderSide, 
    create_market_data_from_ohlcv, RiskManager
)

# Create Interactive Brokers model
model = BrokerageFactory.create_interactive_brokers()

# Create market data
market_data = create_market_data_from_ohlcv(
    timestamp=1640995200,
    open_price=150.0, high=155.0, low=148.0, close=152.0,
    volume=1000000
)

# Validate and execute order
validation = model.validate_order(
    symbol="AAPL",
    side=OrderSide.BUY,
    quantity=100,
    price=151.50,
    order_type=OrderType.LIMIT,
    market_data=market_data,
    cash=20000.0
)

if validation.is_valid:
    fill = model.simulate_execution(
        order_id="TEST001",
        symbol="AAPL",
        side=OrderSide.BUY,
        quantity=100,
        order_type=OrderType.MARKET,
        requested_price=151.50,
        market_data=market_data,
        timestamp=1640995200000
    )
    
    print(f"Executed at ${fill.fill_price:.2f}")
    print(f"Commission: ${fill.commission:.2f}")
    print(f"Total cost: ${fill.total_cost:.2f}")
```

## Migration from Previous Implementation

The enhanced execution modeling is designed to be a drop-in replacement that builds on existing QMTL components:

1. **Uses existing classes**: Builds on `ExecutionModel`, `RiskManager`, `MarketHours`
2. **Backward compatibility**: Legacy method signatures still work
3. **Same imports**: Access through `qmtl.sdk` package
4. **Enhanced functionality**: Adds symbol properties, advanced fee models, validation

This approach provides powerful brokerage modeling while maintaining simplicity and integration with the existing QMTL framework.