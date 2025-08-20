# QMTL Brokerage Models

This document describes QMTL's Lean-style brokerage model system that provides realistic trading simulation with comprehensive broker-specific constraints and costs.

## Overview

The brokerage model system implements a complete trading simulation framework similar to QuantConnect's Lean engine, providing:

- **Symbol Properties**: Tick size, lot size, contract multipliers, and trading constraints
- **Market Hours**: Session management and trading time validation
- **Fee Models**: Broker-specific commission structures (percentage, per-share, tiered)
- **Slippage Models**: Price impact simulation based on volume and market conditions
- **Buying Power**: Cash and margin account calculations with leverage
- **Settlement**: T+2 settlement cycles and cash flow management
- **Short Availability**: Short selling constraints and borrow costs
- **Pre-trade Validation**: Comprehensive order validation pipeline

## Core Components

### Brokerage Model Interface

The `IBrokerageModel` interface defines the complete brokerage model contract:

```python
from qmtl.sdk import BrokerageFactory, AccountType

# Create Interactive Brokers margin account
brokerage = BrokerageFactory.create_interactive_brokers(AccountType.MARGIN)

# Create default cash account
default_brokerage = BrokerageFactory.create_default(AccountType.CASH)
```

### Execution Engine

The `EnhancedExecutionEngine` provides the complete order management and execution simulation:

```python
from qmtl.sdk import EnhancedExecutionEngine, OrderSide, OrderType, TimeInForce

# Initialize with brokerage model
engine = EnhancedExecutionEngine(brokerage)

# Submit orders
order_id, validation = engine.submit_order(
    symbol="AAPL",
    side=OrderSide.BUY,
    order_type=OrderType.MARKET,
    quantity=100,
    price=150.0,
    time_in_force=TimeInForce.GTC
)
```

## Available Brokerage Models

### Interactive Brokers Model

Implements Interactive Brokers' trading rules and fee structure:

- **Tiered Commission**: $0.005/share for first 300 shares, decreasing with volume
- **Margin Requirements**: RegT 50% initial margin, 25% maintenance
- **Market Hours**: Pre-market 4:00-9:30 AM, Regular 9:30 AM-4:00 PM, Post-market 4:00-8:00 PM EST
- **Short Availability**: Symbol-specific inventory with realistic borrow costs
- **Extended Hours**: Limit orders only in pre/post market

```python
from qmtl.sdk import BrokerageFactory, AccountType

# Margin account with 2:1 leverage
ib_margin = BrokerageFactory.create_interactive_brokers(AccountType.MARGIN)

# Cash account
ib_cash = BrokerageFactory.create_interactive_brokers(AccountType.CASH)
```

### Default Model

Simplified model for testing and basic use cases:

- **Commission**: 0.1% of trade value with $1 minimum
- **No Slippage**: Zero price impact by default
- **Cash Account**: Full payment required
- **No Restrictions**: Minimal validation

```python
default_model = BrokerageFactory.create_default(AccountType.CASH)
```

## Order Types and Time-in-Force

### Supported Order Types

- **MARKET**: Immediate execution at current market price
- **LIMIT**: Execute only at specified price or better
- **STOP**: Market order triggered at stop price
- **STOP_LIMIT**: Limit order triggered at stop price

### Time-in-Force Options

- **GTC (Good Till Cancelled)**: Order remains active until filled or cancelled
- **DAY**: Order expires at end of trading day
- **IOC (Immediate or Cancel)**: Fill immediately or cancel unfilled portion
- **FOK (Fill or Kill)**: Fill completely or cancel entire order

```python
from qmtl.sdk import OrderType, TimeInForce, OrderSide

# Market order with GTC
engine.submit_order("AAPL", OrderSide.BUY, OrderType.MARKET, 100, 150.0, TimeInForce.GTC)

# Limit order with IOC
engine.submit_order("AAPL", OrderSide.BUY, OrderType.LIMIT, 100, 149.0, TimeInForce.IOC)

# Stop loss with FOK
engine.submit_order("AAPL", OrderSide.SELL, OrderType.STOP, 100, 145.0, TimeInForce.FOK)
```

## Fee Models

### Percentage Fee Model

Commission as percentage of trade value:

```python
from qmtl.sdk import PercentageFeeModel
from decimal import Decimal

# 0.1% commission with $1 minimum
fee_model = PercentageFeeModel(Decimal("0.001"), Decimal("1.00"))
```

### Per-Share Fee Model

Commission per share traded:

```python
from qmtl.sdk import PerShareFeeModel

# $0.005 per share with $1 minimum, $10 maximum
fee_model = PerShareFeeModel(
    per_share=Decimal("0.005"),
    minimum=Decimal("1.00"),
    maximum=Decimal("10.00")
)
```

### Fixed Fee Model

Flat commission per trade:

```python
from qmtl.sdk import FixedFeeModel

# $5 per trade
fee_model = FixedFeeModel(Decimal("5.00"))
```

## Slippage Models

### Volume Share Slippage

Price impact based on order size relative to volume:

```python
from qmtl.sdk import VolumeShareSlippageModel

# 0.1 price impact coefficient, 2.5% volume limit
slippage_model = VolumeShareSlippageModel(
    price_impact=0.1,
    volume_limit=0.025
)
```

### Null Slippage

No price impact (default for testing):

```python
from qmtl.sdk.brokerage_models import NullSlippageModel

slippage_model = NullSlippageModel()
```

## Portfolio Management

### Portfolio State

The execution engine maintains portfolio state including cash, positions, and margin:

```python
# Get portfolio summary
market_prices = {"AAPL": 155.0, "MSFT": 300.0}
summary = engine.get_portfolio_summary(market_prices)

print(f"Cash: ${summary['cash']:.2f}")
print(f"Positions: {summary['positions']}")
print(f"Total Value: ${summary['total_value']:.2f}")
print(f"Buying Power: ${summary['buying_power']:.2f}")
```

### Order Management

Track and manage order lifecycle:

```python
# Get all orders
orders = engine.get_orders()

# Get orders for specific symbol
aapl_orders = engine.get_orders(symbol="AAPL")

# Get pending orders
pending_orders = engine.get_orders(status=OrderStatus.PENDING)

# Cancel order
success = engine.cancel_order(order_id)
```

## Market Data Integration

### Real-time Updates

Update market data to trigger order executions:

```python
from qmtl.sdk import MarketData

# Create market data
market_data = MarketData(
    timestamp=int(datetime.now().timestamp()),
    bid=149.50,
    ask=150.50,
    last=150.00,
    volume=100000
)

# Update engine with new data
engine.update_market_data("AAPL", market_data)
```

### OHLCV Integration

Convert OHLCV data to market data:

```python
from qmtl.sdk import create_market_data_from_ohlcv

market_data = create_market_data_from_ohlcv(
    timestamp=int(datetime.now().timestamp()),
    open_price=149.0,
    high=151.0,
    low=148.5,
    close=150.0,
    volume=500000,
    spread_estimate=0.001  # 0.1% spread
)
```

## Validation and Error Handling

### Pre-trade Validation

The system validates orders before submission:

```python
order_id, validation = engine.submit_order(...)

if not validation.is_valid:
    print(f"Order rejected: {validation.errors}")
    print(f"Warnings: {validation.warnings}")
```

### Common Validation Errors

- **Market Closed**: Trading outside market hours
- **Insufficient Buying Power**: Not enough cash/margin
- **Invalid Tick Size**: Price not multiple of minimum increment
- **Invalid Lot Size**: Quantity not multiple of minimum lot
- **Short Unavailable**: Insufficient shortable shares

## Integration with DAG Strategies

The brokerage models can be integrated into QMTL strategy DAGs:

```python
from qmtl.sdk import Strategy, BrokerageFactory, EnhancedExecutionEngine

class TradingStrategy(Strategy):
    def __init__(self):
        super().__init__()
        
        # Initialize brokerage and execution engine
        self.brokerage = BrokerageFactory.create_interactive_brokers()
        self.engine = EnhancedExecutionEngine(self.brokerage)
    
    def on_signal(self, signal_data):
        """Handle trading signals from strategy DAG."""
        if signal_data['action'] == 'BUY':
            order_id, validation = self.engine.submit_order(
                symbol=signal_data['symbol'],
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                quantity=signal_data['quantity'],
                price=signal_data['price']
            )
            
            if validation.is_valid:
                self.log(f"Order submitted: {order_id}")
            else:
                self.log(f"Order rejected: {validation.errors}")
```

## Performance Considerations

### Execution Costs

The brokerage models accurately simulate trading costs:

```python
# Compare costs across brokerages
brokerages = {
    "IB": BrokerageFactory.create_interactive_brokers(),
    "Default": BrokerageFactory.create_default()
}

for name, brokerage in brokerages.items():
    commission = brokerage.fee_model.get_order_fee(
        "AAPL", 1000, 150.0, OrderType.MARKET, OrderSide.BUY
    )
    print(f"{name}: ${commission}")
```

### Slippage Impact

Volume-based slippage affects large orders:

```python
# Small vs large order slippage
market_data = MarketData(timestamp=now, bid=149.5, ask=150.5, last=150.0, volume=100000)

small_slippage = slippage_model.get_slippage("AAPL", market_data, OrderType.MARKET, OrderSide.BUY, 100)
large_slippage = slippage_model.get_slippage("AAPL", market_data, OrderType.MARKET, OrderSide.BUY, 10000)

print(f"Small order slippage: ${small_slippage:.4f}")
print(f"Large order slippage: ${large_slippage:.4f}")
```

## Best Practices

1. **Choose Appropriate Model**: Use Interactive Brokers model for realistic simulation, default for testing
2. **Account Type**: Use margin accounts for leverage strategies, cash for simple buy-and-hold
3. **Market Hours**: Validate trading times to avoid rejected orders
4. **Position Sizing**: Account for buying power limits and margin requirements
5. **Cost Analysis**: Include commission and slippage in strategy evaluation
6. **Risk Management**: Use stop losses and position limits appropriate for account type

## See Also

- [Execution Modeling Documentation](execution_modeling.md)
- [Market Timing Controls](timing_controls.md)
- [Example Strategies](../examples/brokerage_model_demo.py)