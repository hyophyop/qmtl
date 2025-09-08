"""Tests for realistic execution modeling."""

import pytest
import math
from qmtl.sdk.execution_modeling import (
    ExecutionModel,
    MarketData,
    OrderType,
    OrderSide,
    ExecutionFill,
    TimeInForce,
    OrderStatus,
    create_market_data_from_ohlcv,
)
from qmtl.transforms.alpha_performance import (
    calculate_execution_metrics,
    adjust_returns_for_costs,
)


class TestMarketData:
    """Test MarketData functionality."""
    
    def test_market_data_properties(self):
        """Test MarketData calculated properties."""
        market_data = MarketData(
            timestamp=1000,
            bid=99.5,
            ask=100.5,
            last=100.0,
            volume=10000
        )
        
        assert market_data.spread == 1.0
        assert market_data.mid_price == 100.0
        assert market_data.spread_pct == 0.01  # 1% spread
    
    def test_market_data_edge_cases(self):
        """Test MarketData with edge case values."""
        # Zero mid price
        market_data = MarketData(
            timestamp=1000,
            bid=0.0,
            ask=0.0,
            last=0.0,
            volume=1000
        )
        
        assert market_data.spread == 0.0
        assert market_data.mid_price == 0.0
        assert market_data.spread_pct == 0.0


class TestExecutionModel:
    """Test ExecutionModel functionality."""
    
    def test_commission_calculation(self):
        """Test commission calculation with minimum."""
        model = ExecutionModel(
            commission_rate=0.001,  # 0.1%
            commission_minimum=1.0
        )
        
        # Large trade - rate applies
        assert model.calculate_commission(10000) == 10.0
        
        # Small trade - minimum applies
        assert model.calculate_commission(100) == 1.0
    
    def test_slippage_calculation(self):
        """Test slippage calculation for different order types."""
        model = ExecutionModel(
            base_slippage_bps=2.0,
            market_impact_coeff=0.1
        )
        
        market_data = MarketData(
            timestamp=1000,
            bid=99.5,
            ask=100.5,
            last=100.0,
            volume=10000
        )
        
        # Market buy order should have positive slippage
        buy_slippage = model.calculate_slippage(
            market_data, OrderType.MARKET, OrderSide.BUY, 100
        )
        assert buy_slippage > 0
        
        # Market sell order should have negative slippage
        sell_slippage = model.calculate_slippage(
            market_data, OrderType.MARKET, OrderSide.SELL, 100
        )
        assert sell_slippage < 0
        
        # Limit orders should have less slippage
        limit_slippage = model.calculate_slippage(
            market_data, OrderType.LIMIT, OrderSide.BUY, 100
        )
        assert abs(limit_slippage) < abs(buy_slippage)
    
    def test_market_impact_scaling(self):
        """Test that market impact scales with order size."""
        model = ExecutionModel(market_impact_coeff=0.1)
        
        market_data = MarketData(
            timestamp=1000,
            bid=99.5,
            ask=100.5,
            last=100.0,
            volume=10000
        )
        
        # Small order
        small_slippage = model.calculate_slippage(
            market_data, OrderType.MARKET, OrderSide.BUY, 100
        )
        
        # Large order (10x size)
        large_slippage = model.calculate_slippage(
            market_data, OrderType.MARKET, OrderSide.BUY, 1000
        )
        
        # Large order should have more slippage due to market impact
        assert large_slippage > small_slippage
    
    def test_simulate_execution_market_order(self):
        """Test simulation of market order execution."""
        model = ExecutionModel(
            commission_rate=0.001,
            commission_minimum=1.0,
            base_slippage_bps=2.0,
            latency_ms=100
        )
        
        market_data = MarketData(
            timestamp=1000,
            bid=99.5,
            ask=100.5,
            last=100.0,
            volume=10000
        )
        
        fill = model.simulate_execution(
            order_id="test_001",
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=100,
            order_type=OrderType.MARKET,
            requested_price=100.0,
            market_data=market_data,
            timestamp=1000
        )
        
        assert fill.order_id == "test_001"
        assert fill.symbol == "AAPL"
        assert fill.side == OrderSide.BUY
        assert fill.quantity == 100
        assert fill.requested_price == 100.0
        assert fill.fill_price > market_data.ask  # Should include slippage
        assert fill.fill_time == 1100  # Original time + latency
        assert fill.commission >= 1.0  # At least minimum commission
        assert fill.slippage > 0  # Buy order should have positive slippage
    
    def test_simulate_execution_limit_order(self):
        """Test simulation of limit order execution."""
        model = ExecutionModel()
        
        market_data = MarketData(
            timestamp=1000,
            bid=99.5,
            ask=100.5,
            last=100.0,
            volume=10000
        )
        
        fill = model.simulate_execution(
            order_id="test_002",
            symbol="AAPL",
            side=OrderSide.SELL,
            quantity=100,
            order_type=OrderType.LIMIT,
            requested_price=99.0,
            market_data=market_data,
            timestamp=1000
        )
        
        # Limit order should execute closer to requested price
        assert abs(fill.fill_price - 99.0) < abs(fill.fill_price - market_data.bid)
        assert fill.side == OrderSide.SELL
        assert fill.slippage < 0  # Sell order should have negative slippage

    def test_commission_and_slippage_values(self):
        """Validate numeric commission and slippage calculations."""
        model = ExecutionModel(
            commission_rate=0.001,
            commission_minimum=0.0,
            base_slippage_bps=1.0,
            market_impact_coeff=0.0,
        )

        market_data = MarketData(
            timestamp=0,
            bid=99.0,
            ask=101.0,
            last=100.0,
            volume=10000,
        )

        slippage = model.calculate_slippage(
            market_data, OrderType.MARKET, OrderSide.BUY, 100
        )
        expected_slippage = market_data.mid_price * 0.0001 + market_data.spread / 2.0
        assert slippage == pytest.approx(expected_slippage)

        fill = model.simulate_execution(
            order_id="t1",
            symbol="XYZ",
            side=OrderSide.BUY,
            quantity=100,
            order_type=OrderType.MARKET,
            requested_price=100.0,
            market_data=market_data,
            timestamp=0,
        )
        expected_price = market_data.ask + expected_slippage
        expected_commission = expected_price * 100 * 0.001
        assert fill.fill_price == pytest.approx(expected_price)
        assert fill.commission == pytest.approx(expected_commission)
    
    def test_order_validation(self):
        """Test order validation logic."""
        model = ExecutionModel()
        
        market_data = MarketData(
            timestamp=1000,
            bid=99.0,
            ask=101.0,
            last=100.0,
            volume=10000
        )
        
        # Valid orders
        valid, msg = model.validate_order(OrderSide.BUY, 100, 100.0, market_data)
        assert valid
        
        # Invalid quantity
        valid, msg = model.validate_order(OrderSide.BUY, -100, 100.0, market_data)
        assert not valid
        assert "positive" in msg.lower()
        
        # Invalid price
        valid, msg = model.validate_order(OrderSide.BUY, 100, -100.0, market_data)
        assert not valid
        assert "positive" in msg.lower()
        
        # Buy price too high
        valid, msg = model.validate_order(OrderSide.BUY, 100, 150.0, market_data)
        assert not valid
        assert "too far above" in msg.lower()
        
        # Sell price too low
        valid, msg = model.validate_order(OrderSide.SELL, 100, 50.0, market_data)
        assert not valid
        assert "too far below" in msg.lower()


class TestExecutionFill:
    """Test ExecutionFill functionality."""
    
    def test_execution_fill_properties(self):
        """Test ExecutionFill calculated properties."""
        fill = ExecutionFill(
            order_id="test_001",
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=100,
            requested_price=100.0,
            fill_price=100.1,
            fill_time=1100,
            commission=5.0,
            slippage=0.05,
            market_impact=0.02
        )
        
        assert fill.total_cost == 10.0  # commission + abs(slippage * quantity)
        assert abs(fill.execution_shortfall - 0.1) < 1e-6  # abs(fill_price - requested_price)


class TestExecutionCostFunctions:
    """Test execution cost analysis helpers."""

    def test_execution_metrics_calculation(self):
        """Test calculation of execution quality metrics."""
        fills = [
            ExecutionFill("1", "AAPL", OrderSide.BUY, 100, 100.0, 100.05, 1000, 2.0, 0.03, 0.02),
            ExecutionFill("2", "AAPL", OrderSide.SELL, 100, 99.0, 98.97, 1100, 2.0, -0.02, 0.01),
            ExecutionFill("3", "MSFT", OrderSide.BUY, 50, 200.0, 200.1, 1200, 1.5, 0.08, 0.02),
        ]

        metrics = calculate_execution_metrics(fills)

        assert metrics["total_trades"] == 3
        assert metrics["total_volume"] == 250  # 100 + 100 + 50
        assert metrics["total_commission"] == 5.5  # 2.0 + 2.0 + 1.5
        assert metrics["avg_commission_bps"] > 0
        assert metrics["avg_slippage_bps"] > 0
        assert metrics["total_execution_cost"] > 0

    def test_return_adjustment_for_costs(self):
        """Test adjustment of returns for execution costs."""
        fill = ExecutionFill("1", "AAPL", OrderSide.BUY, 100, 100.0, 100.1, 1000, 5.0, 0.05, 0.02)

        raw_returns = [0.02, 0.01, -0.01, 0.03]  # 2%, 1%, -1%, 3%
        adjusted_returns = adjust_returns_for_costs(raw_returns, [fill])

        # Adjusted returns should be lower due to execution costs
        for raw, adj in zip(raw_returns, adjusted_returns):
            assert adj < raw

        assert len(adjusted_returns) == len(raw_returns)

    def test_empty_execution_history(self):
        """Test behavior with no execution history."""
        metrics = calculate_execution_metrics([])
        assert metrics == {}

        raw_returns = [0.02, 0.01, -0.01]
        adjusted_returns = adjust_returns_for_costs(raw_returns, [])
        assert adjusted_returns == raw_returns  # No adjustment if no executions


class TestMarketDataHelpers:
    """Test helper functions for market data creation."""
    
    def test_create_market_data_from_ohlcv(self):
        """Test creation of MarketData from OHLCV."""
        market_data = create_market_data_from_ohlcv(
            timestamp=1000,
            open_price=99.0,
            high=101.0,
            low=98.0,
            close=100.0,
            volume=10000,
            spread_estimate=0.002  # 0.2% spread
        )
        
        assert market_data.timestamp == 1000
        assert market_data.last == 100.0
        assert market_data.volume == 10000
        assert market_data.bid < market_data.ask
        assert abs(market_data.mid_price - 100.0) < 0.01  # Close to close price
        assert market_data.spread_pct == pytest.approx(0.002, rel=0.1)  # Close to estimated spread


def test_integration_execution_workflow():
    """Test integrated execution modeling workflow."""
    # Create execution model
    model = ExecutionModel(
        commission_rate=0.0005,  # 0.05%
        commission_minimum=1.0,
        base_slippage_bps=1.5,
        market_impact_coeff=0.05
    )
    
    # Create market data
    market_data = create_market_data_from_ohlcv(
        timestamp=1000,
        open_price=100.0,
        high=101.0,
        low=99.0,
        close=100.0,
        volume=50000
    )
    
    # Validate order
    valid, msg = model.validate_order(OrderSide.BUY, 1000, 100.5, market_data)
    assert valid
    
    # Simulate execution
    fill = model.simulate_execution(
        order_id="integration_001",
        symbol="TEST",
        side=OrderSide.BUY,
        quantity=1000,
        order_type=OrderType.MARKET,
        requested_price=100.0,
        market_data=market_data,
        timestamp=1000
    )
    
    # Check execution results
    assert fill.quantity == 1000
    assert fill.commission >= 1.0
    assert fill.fill_price > market_data.ask  # Market buy should pay ask + slippage
    assert fill.total_cost > 0
    
    # Add to performance tracker
    metrics = calculate_execution_metrics([fill])
    assert metrics["total_trades"] == 1
    assert metrics["total_volume"] == 1000
    assert metrics["total_execution_cost"] > 0


def test_gtc_limit_order_partial_fills():
    """GTC limit orders should persist and fill across bars."""
    model = ExecutionModel(max_partial_fill=40)

    md1 = MarketData(timestamp=0, bid=99.0, ask=99.0, last=99.0, volume=1000)
    order = model.submit_order(
        order_id="gtc1",
        symbol="AAPL",
        side=OrderSide.BUY,
        quantity=100,
        order_type=OrderType.LIMIT,
        requested_price=100.0,
        tif=TimeInForce.GTC,
        market_data=md1,
        timestamp=0,
    )

    assert order.status == OrderStatus.PARTIALLY_FILLED
    assert order.remaining == 60
    assert len(order.fills) == 1

    md2 = MarketData(timestamp=1, bid=98.5, ask=99.0, last=99.0, volume=1000)
    fills = model.update_open_orders(md2, 1)
    assert len(fills) == 1
    assert order.remaining == 20
    assert order.status == OrderStatus.PARTIALLY_FILLED

    md3 = MarketData(timestamp=2, bid=98.5, ask=99.0, last=99.0, volume=1000)
    fills = model.update_open_orders(md3, 2)
    assert len(fills) == 1
    assert order.status == OrderStatus.FILLED
    assert order.order_id not in model.open_orders
    assert order.remaining == 0
    assert len(order.fills) == 3


def test_ioc_and_fok_time_in_force():
    """IOC and FOK orders handle immediate fill or cancel correctly."""
    model = ExecutionModel(max_partial_fill=50)
    md = MarketData(timestamp=0, bid=99.0, ask=99.0, last=99.0, volume=1000)

    ioc = model.submit_order(
        order_id="ioc1",
        symbol="AAPL",
        side=OrderSide.BUY,
        quantity=100,
        order_type=OrderType.LIMIT,
        requested_price=100.0,
        tif=TimeInForce.IOC,
        market_data=md,
        timestamp=0,
    )

    assert ioc.status == OrderStatus.EXPIRED
    assert len(ioc.fills) == 1
    assert ioc.remaining == 50
    assert ioc.order_id not in model.open_orders

    fok = model.submit_order(
        order_id="fok1",
        symbol="AAPL",
        side=OrderSide.BUY,
        quantity=100,
        order_type=OrderType.LIMIT,
        requested_price=100.0,
        tif=TimeInForce.FOK,
        market_data=md,
        timestamp=0,
    )

    assert fok.status == OrderStatus.EXPIRED
    assert len(fok.fills) == 0
    assert fok.remaining == 100
    assert fok.order_id not in model.open_orders
