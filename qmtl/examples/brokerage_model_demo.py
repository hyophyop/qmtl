"""Example demonstrating QMTL's Lean-style brokerage models.

This example shows how to:
1. Set up different brokerage models
2. Execute trades with realistic constraints
3. Monitor portfolio and execution costs
4. Compare execution across different brokers
"""

from datetime import datetime, timezone
from decimal import Decimal

from qmtl.sdk.brokerage_profiles import BrokerageFactory
from qmtl.sdk.execution_engine import EnhancedExecutionEngine, TimeInForce
from qmtl.sdk.execution_modeling import MarketData, OrderSide, OrderType
from qmtl.sdk.brokerage_models import AccountType


def create_sample_market_data(symbol: str, price: float, volume: float = 100000) -> MarketData:
    """Create sample market data for testing."""
    spread = price * 0.001  # 0.1% spread
    return MarketData(
        timestamp=int(datetime.now(timezone.utc).timestamp()),
        bid=price - spread/2,
        ask=price + spread/2,
        last=price,
        volume=volume
    )


def demonstrate_basic_trading():
    """Demonstrate basic trading with default brokerage model."""
    print("=== Basic Trading with Default Brokerage ===")
    
    # Create default brokerage and execution engine
    brokerage = BrokerageFactory.create_default(AccountType.CASH)
    engine = EnhancedExecutionEngine(brokerage)
    
    print(f"Initialized {brokerage.name} with ${engine.portfolio.cash} cash")
    
    # Create market data
    aapl_data = create_sample_market_data("AAPL", 150.0)
    
    # Submit buy order
    print(f"\nSubmitting buy order: 100 AAPL @ market")
    order_id, validation = engine.submit_order(
        symbol="AAPL",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=100,
        price=150.0,
        market_data=aapl_data
    )
    
    if validation.is_valid:
        order = engine.get_order(order_id)
        print(f"Order {order_id} executed:")
        print(f"  Status: {order.status}")
        print(f"  Filled: {order.filled_quantity} @ ${order.avg_fill_price:.2f}")
        print(f"  Commission: ${order.total_commission}")
    else:
        print(f"Order rejected: {validation.errors}")
    
    # Show portfolio
    portfolio = engine.get_portfolio_summary({"AAPL": 150.0})
    print(f"\nPortfolio Summary:")
    print(f"  Cash: ${portfolio['cash']:.2f}")
    print(f"  Positions: {portfolio['positions']}")
    print(f"  Total Value: ${portfolio['total_value']:.2f}")


def demonstrate_interactive_brokers():
    """Demonstrate trading with Interactive Brokers model."""
    print("\n=== Trading with Interactive Brokers Model ===")
    
    # Create IB margin account
    brokerage = BrokerageFactory.create_interactive_brokers(AccountType.MARGIN)
    engine = EnhancedExecutionEngine(brokerage)
    
    print(f"Initialized {brokerage.name} margin account")
    print(f"Required free buying power: {brokerage.required_free_buying_power_percent:.1%}")
    
    # Test various orders with different symbols
    symbols_data = {
        "AAPL": create_sample_market_data("AAPL", 175.0, 500000),
        "TSLA": create_sample_market_data("TSLA", 250.0, 100000),
        "SPY": create_sample_market_data("SPY", 450.0, 1000000)
    }
    
    orders = [
        ("AAPL", OrderSide.BUY, 100, 175.0),
        ("TSLA", OrderSide.BUY, 50, 250.0),
        ("SPY", OrderSide.BUY, 200, 450.0)
    ]
    
    print(f"\nExecuting multiple orders:")
    total_commission = Decimal("0")
    
    for symbol, side, quantity, price in orders:
        market_data = symbols_data[symbol]
        
        order_id, validation = engine.submit_order(
            symbol=symbol,
            side=side,
            order_type=OrderType.MARKET,
            quantity=quantity,
            price=price,
            market_data=market_data
        )
        
        if validation.is_valid:
            order = engine.get_order(order_id)
            commission = order.total_commission
            total_commission += commission
            
            print(f"  {symbol}: {quantity} shares @ ${order.avg_fill_price:.2f}, "
                  f"commission: ${commission:.2f}")
        else:
            print(f"  {symbol}: Order rejected - {validation.errors}")
    
    print(f"\nTotal commissions paid: ${total_commission:.2f}")
    
    # Show final portfolio with current market prices
    current_prices = {symbol: data.last for symbol, data in symbols_data.items()}
    portfolio = engine.get_portfolio_summary(current_prices)
    
    print(f"\nFinal Portfolio:")
    print(f"  Cash: ${portfolio['cash']:.2f}")
    print(f"  Available Buying Power: ${portfolio['buying_power']:.2f}")
    print(f"  Positions:")
    for symbol, quantity in portfolio['positions'].items():
        value = quantity * current_prices[symbol]
        print(f"    {symbol}: {quantity} shares (${value:.2f})")
    print(f"  Total Portfolio Value: ${portfolio['total_value']:.2f}")


def demonstrate_order_types():
    """Demonstrate different order types and time-in-force."""
    print("\n=== Order Types and Time-in-Force ===")
    
    brokerage = BrokerageFactory.create_interactive_brokers()
    engine = EnhancedExecutionEngine(brokerage)
    
    # Market data with spread
    market_data = create_sample_market_data("MSFT", 300.0, 200000)
    print(f"Market data: bid=${market_data.bid:.2f}, ask=${market_data.ask:.2f}")
    
    # Test different order types
    print(f"\nTesting different order types:")
    
    # 1. Market order (immediate execution)
    order_id, validation = engine.submit_order(
        "MSFT", OrderSide.BUY, OrderType.MARKET, 100, 300.0,
        TimeInForce.GTC, market_data
    )
    order = engine.get_order(order_id)
    print(f"Market Order: {order.status}, filled @ ${order.avg_fill_price:.2f}")
    
    # 2. Limit order below market (pending)
    order_id, validation = engine.submit_order(
        "MSFT", OrderSide.BUY, OrderType.LIMIT, 100, 295.0,  # Below bid
        TimeInForce.GTC, market_data
    )
    order = engine.get_order(order_id)
    print(f"Limit Order (below market): {order.status}")
    
    # 3. Limit order above market (immediate execution)
    order_id, validation = engine.submit_order(
        "MSFT", OrderSide.BUY, OrderType.LIMIT, 100, 305.0,  # Above ask
        TimeInForce.GTC, market_data
    )
    order = engine.get_order(order_id)
    print(f"Limit Order (above market): {order.status}, filled @ ${order.avg_fill_price:.2f}")
    
    # 4. IOC order that can't fill immediately
    order_id, validation = engine.submit_order(
        "MSFT", OrderSide.BUY, OrderType.LIMIT, 100, 290.0,  # Below market
        TimeInForce.IOC, market_data
    )
    order = engine.get_order(order_id)
    print(f"IOC Order (below market): {order.status}")
    
    # Show pending orders
    pending_orders = engine.get_orders(status=None)
    pending_count = len([o for o in pending_orders if o.status.value in ['pending', 'partially_filled']])
    print(f"\nPending orders: {pending_count}")


def demonstrate_short_selling():
    """Demonstrate short selling with availability constraints."""
    print("\n=== Short Selling with Constraints ===")
    
    brokerage = BrokerageFactory.create_interactive_brokers()
    engine = EnhancedExecutionEngine(brokerage)
    
    # Try to short different symbols (some may not be available)
    symbols = ["AAPL", "TSLA", "UNKNOWN_SYMBOL"]
    
    for symbol in symbols:
        market_data = create_sample_market_data(symbol, 100.0)
        
        # Check short availability first
        shortable_qty = brokerage.shortable_provider.get_shortable_quantity(
            symbol, datetime.now()
        )
        borrow_cost = brokerage.shortable_provider.get_borrow_cost(
            symbol, 100, datetime.now()
        )
        
        print(f"\n{symbol}:")
        print(f"  Shortable quantity: {shortable_qty}")
        print(f"  Borrow cost: {borrow_cost}")
        
        if shortable_qty and shortable_qty >= 100:
            # Submit short sell order
            order_id, validation = engine.submit_order(
                symbol, OrderSide.SELL, OrderType.MARKET, 100, 100.0,
                TimeInForce.GTC, market_data
            )
            
            if validation.is_valid:
                order = engine.get_order(order_id)
                print(f"  Short sale executed: {order.status}")
            else:
                print(f"  Short sale rejected: {validation.errors}")
        else:
            print(f"  Insufficient shortable quantity for 100 shares")


def compare_brokerage_costs():
    """Compare execution costs across different brokerages."""
    print("\n=== Brokerage Cost Comparison ===")
    
    # Create different brokerage models
    brokerages = {
        "Default": BrokerageFactory.create_default(),
        "Interactive Brokers": BrokerageFactory.create_interactive_brokers()
    }
    
    # Test trade parameters
    test_trades = [
        ("Small Trade", 100, 50.0),
        ("Medium Trade", 1000, 150.0),
        ("Large Trade", 10000, 300.0)
    ]
    
    print(f"{'Trade Size':<15} {'Brokerage':<20} {'Commission':<12} {'Total Cost':<12}")
    print("-" * 65)
    
    for trade_name, quantity, price in test_trades:
        for brokerage_name, brokerage in brokerages.items():
            # Calculate commission
            commission = brokerage.fee_model.get_order_fee(
                "AAPL", quantity, price, OrderType.MARKET, OrderSide.BUY
            )
            
            # Calculate slippage
            market_data = create_sample_market_data("AAPL", price)
            slippage = brokerage.slippage_model.get_slippage(
                "AAPL", market_data, OrderType.MARKET, OrderSide.BUY, quantity
            )
            
            total_cost = float(commission) + abs(slippage * quantity)
            
            print(f"{trade_name:<15} {brokerage_name:<20} ${commission:<11.2f} ${total_cost:<11.2f}")
        print()


def main():
    """Run all demonstration examples."""
    print("QMTL Brokerage Models Demonstration")
    print("=" * 50)
    
    try:
        demonstrate_basic_trading()
        demonstrate_interactive_brokers()
        demonstrate_order_types()
        demonstrate_short_selling()
        compare_brokerage_costs()
        
        print("\n" + "=" * 50)
        print("Demonstration completed successfully!")
        
    except Exception as e:
        print(f"\nError during demonstration: {e}")
        raise


if __name__ == "__main__":
    main()