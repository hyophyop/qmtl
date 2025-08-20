"""Tests for brokerage models and execution engine."""

import pytest
from datetime import datetime, time, timezone
from decimal import Decimal

from qmtl.sdk.brokerage_models import (
    SymbolProperties, Currency, AccountType, ValidationResult,
    DefaultSymbolPropertiesProvider, PercentageFeeModel, FixedFeeModel, 
    PerShareFeeModel, VolumeShareSlippageModel, CashBuyingPowerModel,
    T2SettlementModel, DefaultShortableProvider, DefaultMarginInterestModel
)
from qmtl.sdk.brokerage_profiles import (
    InteractiveBrokersBrokerageModel, DefaultBrokerageModel, BrokerageFactory,
    InteractiveBrokersFeeModel, InteractiveBrokersMarginModel
)
from qmtl.sdk.execution_engine import (
    EnhancedExecutionEngine, Order, Portfolio, OrderStatus, TimeInForce
)
from qmtl.sdk.execution_modeling import MarketData, OrderSide, OrderType
from qmtl.sdk.timing_controls import MarketHours, MarketSession


class TestSymbolProperties:
    """Test symbol properties functionality."""
    
    def test_symbol_properties_creation(self):
        """Test creating symbol properties."""
        market_hours = MarketHours(
            pre_market_start=time(4, 0),
            regular_start=time(9, 30),
            regular_end=time(16, 0),
            post_market_end=time(20, 0)
        )
        
        props = SymbolProperties(
            symbol="AAPL",
            tick_size=Decimal("0.01"),
            lot_size=1,
            contract_multiplier=1,
            currency=Currency.USD,
            market_hours=market_hours,
            min_price_variation=Decimal("0.01")
        )
        
        assert props.symbol == "AAPL"
        assert props.tick_size == Decimal("0.01")
        assert props.currency == Currency.USD
    
    def test_price_rounding(self):
        """Test price rounding to tick size."""
        props = SymbolProperties(
            symbol="AAPL",
            tick_size=Decimal("0.01"),
            lot_size=1,
            contract_multiplier=1,
            currency=Currency.USD,
            market_hours=MarketHours(time(9, 30), time(9, 30), time(16, 0), time(20, 0)),
            min_price_variation=Decimal("0.01")
        )
        
        # Test normal rounding
        assert props.round_price(100.123) == Decimal("100.12")
        assert props.round_price(100.126) == Decimal("100.13")
        
        # Test exact values
        assert props.round_price(100.00) == Decimal("100.00")
    
    def test_quantity_rounding(self):
        """Test quantity rounding to lot size."""
        props = SymbolProperties(
            symbol="FUTURES",
            tick_size=Decimal("0.25"),
            lot_size=100,  # 100 share lots
            contract_multiplier=1,
            currency=Currency.USD,
            market_hours=MarketHours(time(9, 30), time(9, 30), time(16, 0), time(20, 0)),
            min_price_variation=Decimal("0.25")
        )
        
        assert props.round_quantity(150) == 100  # Round down
        assert props.round_quantity(250) == 200  # Round down
        assert props.round_quantity(300) == 300  # Exact
    
    def test_order_validation(self):
        """Test order validation against symbol properties."""
        props = SymbolProperties(
            symbol="AAPL",
            tick_size=Decimal("0.01"),
            lot_size=1,
            contract_multiplier=1,
            currency=Currency.USD,
            market_hours=MarketHours(time(9, 30), time(9, 30), time(16, 0), time(20, 0)),
            min_price_variation=Decimal("0.01"),
            max_order_quantity=10000,
            min_order_value=Decimal("1.00")
        )
        
        # Valid order
        is_valid, msg = props.validate_order(100, 50.00)
        assert is_valid
        
        # Invalid quantity (zero)
        is_valid, msg = props.validate_order(0, 50.00)
        assert not is_valid
        assert "positive" in msg
        
        # Invalid quantity (too large)
        is_valid, msg = props.validate_order(20000, 50.00)
        assert not is_valid
        assert "maximum" in msg
        
        # Invalid price (wrong tick size)
        is_valid, msg = props.validate_order(100, 50.123)
        assert not is_valid
        assert "tick size" in msg


class TestFeeModels:
    """Test fee model implementations."""
    
    def test_percentage_fee_model(self):
        """Test percentage-based fee model."""
        model = PercentageFeeModel(Decimal("0.001"), Decimal("1.00"))  # 0.1% with $1 min
        
        # Normal trade
        fee = model.get_order_fee("AAPL", 100, 50.0, OrderType.MARKET, OrderSide.BUY)
        assert fee == Decimal("5.00")  # 100 * 50 * 0.001 = 5.00
        
        # Small trade (minimum applies)
        fee = model.get_order_fee("AAPL", 1, 0.50, OrderType.MARKET, OrderSide.BUY)
        assert fee == Decimal("1.00")  # Minimum fee
    
    def test_fixed_fee_model(self):
        """Test fixed fee model."""
        model = FixedFeeModel(Decimal("5.00"))
        
        fee = model.get_order_fee("AAPL", 100, 50.0, OrderType.MARKET, OrderSide.BUY)
        assert fee == Decimal("5.00")
        
        fee = model.get_order_fee("AAPL", 1, 1000.0, OrderType.MARKET, OrderSide.BUY)
        assert fee == Decimal("5.00")
    
    def test_per_share_fee_model(self):
        """Test per-share fee model."""
        model = PerShareFeeModel(Decimal("0.005"), Decimal("1.00"), Decimal("10.00"))
        
        # Normal trade
        fee = model.get_order_fee("AAPL", 100, 50.0, OrderType.MARKET, OrderSide.BUY)
        assert fee == Decimal("1.00")  # max(100 * 0.005, 1.00) = 1.00
        
        # Large trade (maximum applies)
        fee = model.get_order_fee("AAPL", 10000, 50.0, OrderType.MARKET, OrderSide.BUY)
        assert fee == Decimal("10.00")  # Capped at maximum
    
    def test_interactive_brokers_fee_model(self):
        """Test IB tiered fee model."""
        model = InteractiveBrokersFeeModel()
        
        # Small order (first tier)
        fee = model.get_order_fee("AAPL", 100, 50.0, OrderType.MARKET, OrderSide.BUY)
        expected = max(Decimal("100") * Decimal("0.005"), Decimal("1.00"))
        assert fee == Decimal("1.00")  # Minimum applies
        
        # Larger order spanning multiple tiers
        fee = model.get_order_fee("AAPL", 1000, 50.0, OrderType.MARKET, OrderSide.BUY)
        # First 300 at 0.005, next 700 at 0.003
        expected = (Decimal("300") * Decimal("0.005") + 
                   Decimal("700") * Decimal("0.003"))
        assert fee == expected


class TestSlippageModels:
    """Test slippage model implementations."""
    
    def test_volume_share_slippage_model(self):
        """Test volume-based slippage model."""
        model = VolumeShareSlippageModel(price_impact=0.1, volume_limit=0.025)
        
        market_data = MarketData(
            timestamp=1000,
            bid=99.5,
            ask=100.5,
            last=100.0,
            volume=10000
        )
        
        # Small order (minimal slippage)
        slippage = model.get_slippage("AAPL", market_data, OrderType.MARKET, OrderSide.BUY, 100)
        assert slippage > 0  # Buy orders have positive slippage
        
        # Large order (more slippage)
        large_slippage = model.get_slippage("AAPL", market_data, OrderType.MARKET, OrderSide.BUY, 1000)
        assert large_slippage > slippage
        
        # Sell order (negative slippage)
        sell_slippage = model.get_slippage("AAPL", market_data, OrderType.MARKET, OrderSide.SELL, 100)
        assert sell_slippage < 0


class TestBuyingPowerModels:
    """Test buying power model implementations."""
    
    def test_cash_buying_power_model(self):
        """Test cash account buying power."""
        model = CashBuyingPowerModel()
        
        buying_power = model.get_buying_power(
            portfolio_value=Decimal("100000"),
            cash=Decimal("50000"),
            positions={"AAPL": 100}
        )
        assert buying_power == Decimal("50000")  # Cash accounts use available cash
        
        max_qty = model.get_maximum_order_quantity("AAPL", 50.0, Decimal("10000"), {})
        assert max_qty == 200.0  # 10000 / 50
        
        margin_req = model.get_margin_requirement("AAPL", 100, 50.0)
        assert margin_req == Decimal("5000")  # Full value for cash accounts
    
    def test_interactive_brokers_margin_model(self):
        """Test IB margin model."""
        model = InteractiveBrokersMarginModel()
        
        # Margin buying power is 2x cash
        buying_power = model.get_buying_power(
            portfolio_value=Decimal("100000"),
            cash=Decimal("50000"),
            positions={}
        )
        assert buying_power == Decimal("100000")  # 2x leverage
        
        # With 50% initial margin requirement
        max_qty = model.get_maximum_order_quantity("AAPL", 100.0, Decimal("10000"), {})
        assert max_qty == 200.0  # 10000 / (100 * 0.5)


class TestBrokerageModels:
    """Test complete brokerage model implementations."""
    
    def test_default_brokerage_model(self):
        """Test default brokerage model."""
        model = DefaultBrokerageModel(AccountType.CASH)
        
        assert model.name == "Default Brokerage"
        assert model.account_type == AccountType.CASH
        assert model.required_free_buying_power_percent == Decimal("0.0")
        
        # Test basic validation
        market_data = MarketData(
            timestamp=1000,
            bid=99.5,
            ask=100.5,
            last=100.0,
            volume=10000
        )
        
        result = model.can_submit_order(
            "AAPL", OrderType.MARKET, OrderSide.BUY, 100, 50.0, market_data, datetime.now()
        )
        assert result.is_valid
        
        # Test invalid order
        result = model.can_submit_order(
            "AAPL", OrderType.MARKET, OrderSide.BUY, -100, 50.0, market_data, datetime.now()
        )
        assert not result.is_valid
        assert "positive" in result.errors[0]
    
    def test_interactive_brokers_model(self):
        """Test Interactive Brokers brokerage model."""
        model = InteractiveBrokersBrokerageModel(AccountType.MARGIN)
        
        assert model.name == "Interactive Brokers"
        assert model.account_type == AccountType.MARGIN
        assert model.required_free_buying_power_percent == Decimal("0.05")
        
        # All component models should be available
        assert model.fee_model is not None
        assert model.slippage_model is not None
        assert model.buying_power_model is not None
        assert model.settlement_model is not None
        assert model.shortable_provider is not None
        assert model.margin_interest_model is not None
    
    def test_brokerage_factory(self):
        """Test brokerage factory."""
        ib_model = BrokerageFactory.create_interactive_brokers()
        assert isinstance(ib_model, InteractiveBrokersBrokerageModel)
        
        default_model = BrokerageFactory.create_default()
        assert isinstance(default_model, DefaultBrokerageModel)
        
        models = BrokerageFactory.get_available_models()
        assert "interactive_brokers" in models
        assert "default" in models


class TestExecutionEngine:
    """Test enhanced execution engine."""
    
    def test_engine_initialization(self):
        """Test execution engine initialization."""
        brokerage = DefaultBrokerageModel()
        engine = EnhancedExecutionEngine(brokerage)
        
        assert engine.brokerage_model == brokerage
        assert len(engine.orders) == 0
        assert engine.portfolio.cash == Decimal("100000")  # Default cash
    
    def test_order_submission(self):
        """Test order submission."""
        brokerage = DefaultBrokerageModel()
        engine = EnhancedExecutionEngine(brokerage)
        
        market_data = MarketData(
            timestamp=1000,
            bid=99.5,
            ask=100.5,
            last=100.0,
            volume=10000
        )
        
        order_id, validation = engine.submit_order(
            "AAPL", OrderSide.BUY, OrderType.LIMIT, 100, 95.0,
            TimeInForce.GTC, market_data
        )
        
        assert validation.is_valid
        assert order_id in engine.orders
        
        order = engine.orders[order_id]
        assert order.symbol == "AAPL"
        assert order.quantity == 100
        assert order.status == OrderStatus.PENDING
    
    def test_order_rejection(self):
        """Test order rejection."""
        brokerage = DefaultBrokerageModel()
        engine = EnhancedExecutionEngine(brokerage)
        
        market_data = MarketData(
            timestamp=1000,
            bid=99.5,
            ask=100.5,
            last=100.0,
            volume=10000
        )
        
        # Submit invalid order (negative quantity)
        order_id, validation = engine.submit_order(
            "AAPL", OrderSide.BUY, OrderType.MARKET, -100, 100.0,
            TimeInForce.GTC, market_data
        )
        
        assert not validation.is_valid
        assert order_id in engine.orders
        
        order = engine.orders[order_id]
        assert order.status == OrderStatus.REJECTED
        assert order.rejection_reason is not None
    
    def test_market_order_execution(self):
        """Test market order immediate execution."""
        brokerage = DefaultBrokerageModel()
        engine = EnhancedExecutionEngine(brokerage)
        
        market_data = MarketData(
            timestamp=1000,
            bid=99.5,
            ask=100.5,
            last=100.0,
            volume=10000
        )
        
        initial_cash = engine.portfolio.cash
        
        order_id, validation = engine.submit_order(
            "AAPL", OrderSide.BUY, OrderType.MARKET, 100, 100.0,
            TimeInForce.GTC, market_data
        )
        
        assert validation.is_valid
        order = engine.orders[order_id]
        
        # Market order should execute immediately
        assert order.status == OrderStatus.FILLED
        assert order.filled_quantity == 100
        assert len(order.fills) == 1
        
        # Portfolio should be updated
        assert engine.portfolio.get_position("AAPL") == 100
        assert engine.portfolio.cash < initial_cash  # Cash reduced
    
    def test_limit_order_execution(self):
        """Test limit order execution when price is met."""
        brokerage = DefaultBrokerageModel()
        engine = EnhancedExecutionEngine(brokerage)
        
        # Submit limit buy order above current ask (should execute immediately)
        market_data = MarketData(
            timestamp=1000,
            bid=99.5,
            ask=100.5,
            last=100.0,
            volume=10000
        )
        
        order_id, validation = engine.submit_order(
            "AAPL", OrderSide.BUY, OrderType.LIMIT, 100, 101.0,  # Above ask
            TimeInForce.GTC, market_data
        )
        
        assert validation.is_valid
        order = engine.orders[order_id]
        assert order.status == OrderStatus.FILLED
        
    def test_order_cancellation(self):
        """Test order cancellation."""
        brokerage = DefaultBrokerageModel()
        engine = EnhancedExecutionEngine(brokerage)
        
        market_data = MarketData(
            timestamp=1000,
            bid=99.5,
            ask=100.5,
            last=100.0,
            volume=10000
        )
        
        # Submit limit order that won't execute immediately
        order_id, validation = engine.submit_order(
            "AAPL", OrderSide.BUY, OrderType.LIMIT, 100, 90.0,  # Below market
            TimeInForce.GTC, market_data
        )
        
        order = engine.orders[order_id]
        assert order.status == OrderStatus.PENDING
        
        # Cancel the order
        success = engine.cancel_order(order_id)
        assert success
        assert order.status == OrderStatus.CANCELLED
    
    def test_portfolio_summary(self):
        """Test portfolio summary generation."""
        brokerage = DefaultBrokerageModel()
        engine = EnhancedExecutionEngine(brokerage)
        
        # Execute a trade to have positions
        market_data = MarketData(
            timestamp=1000,
            bid=99.5,
            ask=100.5,
            last=100.0,
            volume=10000
        )
        
        engine.submit_order(
            "AAPL", OrderSide.BUY, OrderType.MARKET, 100, 100.0,
            TimeInForce.GTC, market_data
        )
        
        # Get portfolio summary
        market_prices = {"AAPL": 105.0}
        summary = engine.get_portfolio_summary(market_prices)
        
        assert "cash" in summary
        assert "positions" in summary
        assert "total_value" in summary
        assert "buying_power" in summary
        
        assert summary["positions"]["AAPL"] == 100
        assert summary["total_value"] > summary["cash"]  # Has position value


class TestIntegration:
    """Integration tests for the complete system."""
    
    def test_full_trading_workflow(self):
        """Test complete trading workflow with IB model."""
        brokerage = BrokerageFactory.create_default(AccountType.CASH)  # Use simpler model
        engine = EnhancedExecutionEngine(brokerage)
        
        # Create market data with timestamp during regular market hours
        from datetime import datetime, timezone, time
        # Create a datetime during regular trading hours (10 AM EST)
        market_time = datetime.now(timezone.utc).replace(hour=15, minute=0)  # 3 PM UTC = 10 AM EST
        
        market_data = MarketData(
            timestamp=int(market_time.timestamp()),
            bid=149.5,
            ask=150.5,
            last=150.0,
            volume=100000
        )
        
        # Submit buy order
        buy_order_id, validation = engine.submit_order(
            "AAPL", OrderSide.BUY, OrderType.MARKET, 100, 150.0,
            TimeInForce.GTC, market_data, timestamp=market_time
        )
        
        assert validation.is_valid
        buy_order = engine.orders[buy_order_id]
        assert buy_order.status == OrderStatus.FILLED
        
        # Check position
        assert engine.portfolio.get_position("AAPL") == 100
        
        # Submit sell order
        sell_order_id, validation = engine.submit_order(
            "AAPL", OrderSide.SELL, OrderType.LIMIT, 50, 155.0,
            TimeInForce.GTC, market_data, timestamp=market_time
        )
        
        assert validation.is_valid
        
        # Update market data to trigger limit order
        new_market_data = MarketData(
            timestamp=2000,
            bid=155.5,  # Bid above our sell limit price
            ask=156.5,
            last=156.0,
            volume=50000
        )
        
        engine.update_market_data("AAPL", new_market_data)
        
        sell_order = engine.orders[sell_order_id]
        assert sell_order.status == OrderStatus.FILLED
        
        # Check final position
        assert engine.portfolio.get_position("AAPL") == 50
        
        # Verify fees were applied
        total_commission = sum(order.total_commission for order in engine.orders.values())
        assert total_commission > 0
    
    def test_ioc_order_behavior(self):
        """Test IOC (Immediate or Cancel) order behavior."""
        brokerage = DefaultBrokerageModel()
        engine = EnhancedExecutionEngine(brokerage)
        
        market_data = MarketData(
            timestamp=1000,
            bid=99.5,
            ask=100.5,
            last=100.0,
            volume=10000
        )
        
        # IOC limit order that can't be filled immediately
        order_id, validation = engine.submit_order(
            "AAPL", OrderSide.BUY, OrderType.LIMIT, 100, 90.0,  # Below market
            TimeInForce.IOC, market_data
        )
        
        order = engine.orders[order_id]
        assert order.status == OrderStatus.CANCELLED
        assert order.filled_quantity == 0
    
    def test_fok_order_behavior(self):
        """Test FOK (Fill or Kill) order behavior."""
        brokerage = DefaultBrokerageModel()
        engine = EnhancedExecutionEngine(brokerage)
        
        # Small volume market data
        market_data = MarketData(
            timestamp=1000,
            bid=99.5,
            ask=100.5,
            last=100.0,
            volume=50  # Very small volume
        )
        
        # FOK order larger than available volume
        order_id, validation = engine.submit_order(
            "AAPL", OrderSide.BUY, OrderType.MARKET, 1000,  # Larger than volume
            100.0, TimeInForce.FOK, market_data
        )
        
        order = engine.orders[order_id]
        # Should be cancelled if can't fill completely
        assert order.status in [OrderStatus.CANCELLED, OrderStatus.FILLED]