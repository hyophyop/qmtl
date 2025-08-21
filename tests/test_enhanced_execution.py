"""Tests for enhanced execution modeling functionality."""

import pytest
from decimal import Decimal

from qmtl.sdk import (
    ExecutionModel, BrokerageFactory, OrderType, OrderSide, TimeInForce,
    AccountType, SymbolProperties, ValidationResult, MarketData,
    InteractiveBrokersFeeModel, PercentageFeeModel, VolumeShareSlippageModel,
    CashBuyingPowerModel, MarginBuyingPowerModel, create_market_data_from_ohlcv,
    RiskManager, RiskViolationType, PositionInfo
)


class TestSymbolProperties:
    """Test symbol properties functionality."""
    
    def test_symbol_properties_creation(self):
        """Test creating symbol properties."""
        props = SymbolProperties(
            symbol="AAPL",
            tick_size=Decimal("0.01"),
            lot_size=1,
            contract_multiplier=1,
            margin_requirement=Decimal("0.30")
        )
        
        assert props.symbol == "AAPL"
        assert props.tick_size == Decimal("0.01")
        assert props.lot_size == 1
    
    def test_price_rounding(self):
        """Test price rounding to tick size."""
        props = SymbolProperties("AAPL", Decimal("0.01"))
        
        # Test rounding down
        rounded = props.round_price(100.234)
        assert rounded == Decimal("100.23")
        
        # Test rounding up
        rounded = props.round_price(100.236)
        assert rounded == Decimal("100.24")
        
        # Test exact tick
        rounded = props.round_price(100.25)
        assert rounded == Decimal("100.25")
    
    def test_quantity_rounding(self):
        """Test quantity rounding to lot size."""
        props = SymbolProperties("AAPL", Decimal("0.01"), lot_size=100)
        
        # Test rounding down
        rounded = props.round_quantity(250)
        assert rounded == 200
        
        # Test rounding up
        rounded = props.round_quantity(350) 
        assert rounded == 300
        
        # Test exact lot
        rounded = props.round_quantity(300)
        assert rounded == 300


class TestFeeModels:
    """Test different fee models."""
    
    def test_percentage_fee_model(self):
        """Test percentage-based fee calculation."""
        model = PercentageFeeModel(commission_rate=0.001, minimum_fee=1.0)
        
        # Small trade - minimum fee applies
        fee = model.calculate_fee("AAPL", 10, 100.0)
        assert fee == 1.0
        
        # Large trade - percentage applies
        fee = model.calculate_fee("AAPL", 1000, 100.0)
        assert fee == 100.0  # 0.1% of $100,000
    
    def test_interactive_brokers_fee_model(self):
        """Test IB tiered fee model."""
        model = InteractiveBrokersFeeModel()
        
        # First tier: 300 shares at $0.005
        fee = model.calculate_fee("AAPL", 300, 100.0)
        assert fee == 1.5  # 300 * 0.005
        
        # Multiple tiers: 500 shares
        fee = model.calculate_fee("AAPL", 500, 100.0)
        expected = 300 * 0.005 + 200 * 0.003  # First 300 + next 200
        assert fee == expected
        
        # Minimum fee applies
        fee = model.calculate_fee("AAPL", 10, 100.0)
        assert fee == 1.0


class TestSlippageModels:
    """Test slippage calculation models."""
    
    def test_volume_share_slippage(self):
        """Test volume share slippage model."""
        model = VolumeShareSlippageModel(price_impact_coefficient=0.1, max_volume_share=0.025)
        
        market_data = MarketData(
            timestamp=1640995200,
            bid=99.50,
            ask=100.50,
            last=100.00,
            volume=1000000
        )
        
        # Small order - minimal slippage
        slippage = model.calculate_slippage(market_data, OrderSide.BUY, 1000)
        assert slippage > 0  # Buy orders pay slippage
        
        # Large order - more slippage
        large_slippage = model.calculate_slippage(market_data, OrderSide.BUY, 10000)
        assert large_slippage > slippage
        
        # Sell order - negative slippage
        sell_slippage = model.calculate_slippage(market_data, OrderSide.SELL, 1000)
        assert sell_slippage < 0


class TestBuyingPowerModels:
    """Test buying power calculation models."""
    
    def test_cash_buying_power(self):
        """Test cash account buying power."""
        model = CashBuyingPowerModel()
        
        # Full cash available
        power = model.get_buying_power(10000.0, {})
        assert power == 10000.0
        
        # No negative buying power
        power = model.get_buying_power(-1000.0, {})
        assert power == 0.0
    
    def test_margin_buying_power(self):
        """Test margin account buying power."""
        model = MarginBuyingPowerModel(leverage=2.0, maintenance_margin=0.25)
        
        # 2x leverage
        power = model.get_buying_power(10000.0, {})
        assert power == 20000.0
        
        # No negative buying power
        power = model.get_buying_power(-1000.0, {})
        assert power == 0.0


class TestExecutionModel:
    """Test enhanced execution model."""
    
    def test_execution_model_creation(self):
        """Test creating execution model with custom components."""
        model = ExecutionModel(
            fee_model=PercentageFeeModel(0.001, 1.0),
            slippage_model=VolumeShareSlippageModel(0.1, 0.025),
            buying_power_model=CashBuyingPowerModel(),
            account_type=AccountType.CASH
        )
        
        assert model.account_type == AccountType.CASH
        assert isinstance(model.fee_model, PercentageFeeModel)
    
    def test_order_validation(self):
        """Test comprehensive order validation."""
        # Set up symbol properties
        symbol_props = {
            "AAPL": SymbolProperties("AAPL", Decimal("0.01"), 1, 1, Decimal("0.30"))
        }
        
        model = ExecutionModel(symbol_properties=symbol_props)
        
        market_data = MarketData(
            timestamp=1640995200,
            bid=99.50,
            ask=100.50,
            last=100.00,
            volume=1000000
        )
        
        # Valid order
        result = model.validate_order(
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=100,
            price=100.00,
            order_type=OrderType.LIMIT,
            market_data=market_data,
            cash=20000.0
        )
        assert result.is_valid
        
        # Invalid price (wrong tick size)
        result = model.validate_order(
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=100,
            price=100.234,
            order_type=OrderType.LIMIT,
            market_data=market_data,
            cash=20000.0
        )
        assert result.is_valid  # Should be valid with adjustment
        assert result.adjusted_price == 100.23
        
        # Insufficient buying power
        result = model.validate_order(
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=1000,
            price=100.00,
            order_type=OrderType.LIMIT,
            market_data=market_data,
            cash=50000.0  # Need $100,000 but only have $50,000
        )
        assert not result.is_valid
        assert "Insufficient buying power" in result.message
    
    def test_execution_simulation(self):
        """Test order execution simulation."""
        model = ExecutionModel()
        
        market_data = MarketData(
            timestamp=1640995200,
            bid=99.50,
            ask=100.50,
            last=100.00,
            volume=1000000
        )
        
        fill = model.simulate_execution(
            order_id="TEST001",
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=100,
            order_type=OrderType.MARKET,
            requested_price=100.00,
            market_data=market_data,
            timestamp=1640995200000,
            time_in_force=TimeInForce.DAY
        )
        
        assert fill.order_id == "TEST001"
        assert fill.symbol == "AAPL"
        assert fill.side == OrderSide.BUY
        assert fill.quantity == 100
        assert fill.commission > 0
        assert fill.time_in_force == TimeInForce.DAY


class TestBrokerageFactory:
    """Test brokerage factory for creating pre-configured models."""
    
    def test_interactive_brokers_factory(self):
        """Test IB model creation."""
        model = BrokerageFactory.create_interactive_brokers()
        
        assert model.account_type == AccountType.MARGIN
        assert isinstance(model.fee_model, InteractiveBrokersFeeModel)
        assert isinstance(model.slippage_model, VolumeShareSlippageModel)
        assert isinstance(model.buying_power_model, MarginBuyingPowerModel)
        assert model.latency_ms == 50
    
    def test_simple_cash_factory(self):
        """Test simple cash model creation."""
        model = BrokerageFactory.create_simple_cash_model()
        
        assert model.account_type == AccountType.CASH
        assert isinstance(model.fee_model, PercentageFeeModel)
        assert isinstance(model.buying_power_model, CashBuyingPowerModel)


class TestRiskManagementIntegration:
    """Test integration with risk management."""
    
    def test_position_size_validation(self):
        """Test position size validation."""
        risk_manager = RiskManager(
            max_leverage=2.0,
            max_drawdown_pct=0.10,
            position_size_limit_pct=0.05  # 5% max position
        )
        
        # Valid position size
        is_valid, violation, adjusted = risk_manager.validate_position_size(
            symbol="AAPL",
            proposed_quantity=50,
            current_price=100.0,
            portfolio_value=100000.0,
            current_positions={}
        )
        assert is_valid
        
        # Oversized position
        is_valid, violation, adjusted = risk_manager.validate_position_size(
            symbol="AAPL",
            proposed_quantity=100,  # $10,000 position = 10% of portfolio
            current_price=100.0,
            portfolio_value=100000.0,
            current_positions={}
        )
        assert not is_valid
        assert violation.violation_type == RiskViolationType.POSITION_SIZE_LIMIT
        assert adjusted == 50  # Should be adjusted to 5% max
    
    def test_portfolio_risk_validation(self):
        """Test portfolio-level risk validation."""
        risk_manager = RiskManager(max_concentration_pct=0.20)
        
        positions = {
            "AAPL": PositionInfo(
                symbol="AAPL",
                quantity=250,
                market_value=25000.0,  # 25% of portfolio
                unrealized_pnl=0.0,
                entry_price=100.0,
                current_price=100.0
            )
        }
        
        violations = risk_manager.validate_portfolio_risk(
            positions=positions,
            portfolio_value=100000.0,
            timestamp=1640995200
        )
        
        assert len(violations) == 1
        assert violations[0].violation_type == RiskViolationType.CONCENTRATION_LIMIT


class TestMarketDataUtilities:
    """Test market data utility functions."""
    
    def test_create_market_data_from_ohlcv(self):
        """Test creating market data from OHLCV."""
        market_data = create_market_data_from_ohlcv(
            timestamp=1640995200,
            open_price=100.0,
            high=102.0,
            low=98.0,
            close=101.0,
            volume=1000000,
            spread_estimate=0.001
        )
        
        assert market_data.timestamp == 1640995200
        assert market_data.last == 101.0
        assert market_data.volume == 1000000
        assert market_data.bid < market_data.ask
        assert market_data.spread == market_data.ask - market_data.bid