"""Enhanced execution modeling demonstration using QMTL's existing framework.

This example shows how to use the enhanced ExecutionModel with brokerage-specific 
features while building on existing QMTL components.
"""

from qmtl.sdk import (
    ExecutionModel, BrokerageFactory, OrderType, OrderSide, TimeInForce,
    MarketData, AccountType, RiskManager, PositionInfo, create_market_data_from_ohlcv
)


def main():
    """Demonstrate enhanced execution modeling with realistic brokerage simulation."""
    
    print("=== Enhanced QMTL Execution Modeling Demo ===")
    
    # Create Interactive Brokers execution model
    ib_model = BrokerageFactory.create_interactive_brokers()
    print("✓ Created Interactive Brokers execution model")
    
    # Create simple cash model for comparison
    cash_model = BrokerageFactory.create_simple_cash_model()
    print("✓ Created simple cash execution model")
    
    # Create sample market data
    market_data = create_market_data_from_ohlcv(
        timestamp=1640995200,  # 2022-01-01
        open_price=150.0,
        high=155.0,
        low=148.0,
        close=152.0,
        volume=1000000,
        spread_estimate=0.001
    )
    print(f"✓ Created market data: bid=${market_data.bid:.2f}, ask=${market_data.ask:.2f}")
    
    # Test order validation with symbol properties
    symbol = "AAPL"
    quantity = 100.5  # Non-round lot
    price = 151.234   # Non-tick-size price
    
    print(f"\n--- Order Validation ---")
    print(f"Original order: {quantity} shares at ${price:.3f}")
    
    validation = ib_model.validate_order(
        symbol=symbol,
        side=OrderSide.BUY,
        quantity=quantity,
        price=price,
        order_type=OrderType.LIMIT,
        market_data=market_data,
        cash=20000.0
    )
    
    if validation.is_valid:
        print(f"✓ Order valid: {validation.message}")
        if validation.adjusted_quantity or validation.adjusted_price:
            print(f"  Adjusted to: {validation.adjusted_quantity or quantity} shares at ${validation.adjusted_price or price:.2f}")
    else:
        print(f"✗ Order invalid: {validation.message}")
    
    # Simulate order execution
    print(f"\n--- Order Execution ---")
    
    fill = ib_model.simulate_execution(
        order_id="TEST001",
        symbol=symbol,
        side=OrderSide.BUY,
        quantity=validation.adjusted_quantity or quantity,
        order_type=OrderType.MARKET,
        requested_price=validation.adjusted_price or price,
        market_data=market_data,
        timestamp=1640995200000,
        time_in_force=TimeInForce.DAY
    )
    
    print(f"Execution results:")
    print(f"  Fill price: ${fill.fill_price:.2f}")
    print(f"  Commission: ${fill.commission:.2f}")
    print(f"  Slippage: ${fill.slippage:.4f}")
    print(f"  Total cost: ${fill.total_cost:.2f}")
    
    # Compare with cash model
    cash_fill = cash_model.simulate_execution(
        order_id="TEST002",
        symbol=symbol,
        side=OrderSide.BUY,
        quantity=100,
        order_type=OrderType.MARKET,
        requested_price=price,
        market_data=market_data,
        timestamp=1640995200000
    )
    
    print(f"\nCash model comparison:")
    print(f"  IB commission: ${fill.commission:.2f}")
    print(f"  Cash commission: ${cash_fill.commission:.2f}")
    print(f"  Difference: ${fill.commission - cash_fill.commission:.2f}")
    
    # Risk management example
    print(f"\n--- Risk Management ---")
    
    risk_manager = RiskManager(
        max_leverage=2.0,
        max_drawdown_pct=0.10,
        max_concentration_pct=0.15,
        position_size_limit_pct=0.08
    )
    
    # Test position size validation
    portfolio_value = 100000.0
    proposed_quantity = 1000  # Large position
    current_price = 152.0
    
    is_valid, violation, adjusted_qty = risk_manager.validate_position_size(
        symbol=symbol,
        proposed_quantity=proposed_quantity,
        current_price=current_price,
        portfolio_value=portfolio_value,
        current_positions={}
    )
    
    if not is_valid:
        print(f"✗ Position size rejected: {violation.description}")
        print(f"  Suggested size: {adjusted_qty:.0f} shares")
    else:
        print(f"✓ Position size approved: {proposed_quantity} shares")
    
    # Portfolio risk check
    positions = {
        "AAPL": PositionInfo(
            symbol="AAPL",
            quantity=adjusted_qty,
            market_value=adjusted_qty * current_price,
            unrealized_pnl=0.0,
            entry_price=current_price,
            current_price=current_price
        )
    }
    
    violations = risk_manager.validate_portfolio_risk(
        positions=positions,
        portfolio_value=portfolio_value,
        timestamp=1640995200
    )
    
    if violations:
        print(f"⚠ Portfolio risk violations:")
        for v in violations:
            print(f"  {v.violation_type.value}: {v.description}")
    else:
        print("✓ Portfolio passes all risk checks")
    
    print(f"\n--- Summary ---")
    print(f"Enhanced execution modeling provides:")
    print(f"• Symbol-specific properties (tick size, lot size)")
    print(f"• Realistic fee models (IB tiered commission)")
    print(f"• Volume-based slippage calculation")
    print(f"• Comprehensive order validation")
    print(f"• Risk management integration")
    print(f"• Market hours and session support")
    
    print(f"\nAll features integrate with existing QMTL framework!")


if __name__ == "__main__":
    main()