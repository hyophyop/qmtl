"""Comprehensive integration test for all backtest accuracy enhancements."""

import pytest
from datetime import datetime, timezone
from qmtl.runtime.sdk import Runner, Strategy, StreamInput
from qmtl.runtime.sdk.backtest_validation import BacktestDataValidator
from qmtl.runtime.sdk.execution_modeling import ExecutionModel, OrderSide, OrderType, create_market_data_from_ohlcv
from qmtl.runtime.sdk.timing_controls import TimingController
from qmtl.runtime.sdk.risk_management import RiskManager, PositionInfo


def test_comprehensive_backtest_accuracy_enhancements():
    """Integration test for all backtest accuracy enhancements."""
    
    # 1. Data Validation Testing
    validator = BacktestDataValidator(
        max_price_change_pct=0.05,  # 5% max change
        min_price=1.0,
        max_gap_tolerance_sec=120,  # 2 minutes
        required_fields=["close", "volume"]
    )
    
    # Clean data should pass validation
    clean_data = [
        (1000, {"close": 100.0, "volume": 10000}),
        (1060, {"close": 102.0, "volume": 12000}),  # 2% increase
        (1120, {"close": 101.0, "volume": 8000}),   # 1% decrease
    ]
    
    report = validator.validate_time_series(clean_data, interval_sec=60)
    assert report.data_quality_score == 1.0
    assert not report.has_issues
    
    # 2. Execution Modeling Testing
    execution_model = ExecutionModel(
        commission_rate=0.001,
        commission_minimum=1.0,
        base_slippage_bps=2.0,
        market_impact_coeff=0.1
    )
    
    market_data = create_market_data_from_ohlcv(
        timestamp=1000,
        open_price=100.0,
        high=102.0,
        low=99.0,
        close=101.0,
        volume=50000
    )
    
    # Simulate a realistic execution
    fill = execution_model.simulate_execution(
        order_id="test_001",
        symbol="AAPL",
        side=OrderSide.BUY,
        quantity=100,
        order_type=OrderType.MARKET,
        requested_price=101.0,
        market_data=market_data,
        timestamp=1000
    )
    
    assert fill.quantity == 100
    assert fill.commission >= 1.0  # At least minimum commission
    assert fill.fill_price > market_data.ask  # Should include slippage
    assert fill.total_cost > 0
    
    # 3. Timing Controls Testing
    timing_controller = TimingController(
        allow_pre_post_market=False,
        require_regular_hours=True
    )
    
    # Wednesday 10:30 AM should be valid
    valid_time = datetime(2024, 1, 3, 10, 30, tzinfo=timezone.utc)
    is_valid, reason, session = timing_controller.validate_timing(valid_time)
    assert is_valid
    
    # Saturday should be invalid
    invalid_time = datetime(2024, 1, 6, 10, 30, tzinfo=timezone.utc)
    is_valid, reason, session = timing_controller.validate_timing(invalid_time)
    assert not is_valid
    
    # 4. Risk Management Testing
    risk_manager = RiskManager(
        max_leverage=2.0,
        max_concentration_pct=0.25,
        position_size_limit_pct=0.10,
        max_drawdown_pct=0.15
    )
    
    # Test position size calculation
    position_size = risk_manager.calculate_position_size(
        symbol="AAPL",
        target_allocation_pct=0.08,
        current_price=101.0,
        portfolio_value=100000
    )
    
    expected_size = (100000 * 0.08) / 101.0  # 8% of portfolio
    assert abs(position_size - expected_size) < 0.1
    
    # Test position validation
    is_valid, violation, adjusted = risk_manager.validate_position_size(
        symbol="AAPL",
        proposed_quantity=position_size,
        current_price=101.0,
        portfolio_value=100000,
        current_positions={}
    )
    
    assert is_valid
    assert violation is None
    
    # 5. Portfolio Risk Validation
    positions = {
        "AAPL": PositionInfo("AAPL", position_size, position_size * 101.0, 0, 101.0, 101.0),
        "TSLA": PositionInfo("TSLA", 20, 20 * 200, 0, 200, 200),  # $4000 position
    }
    
    violations = risk_manager.validate_portfolio_risk(
        positions=positions,
        portfolio_value=100000,
        timestamp=1000
    )
    
    # Should have no violations since positions are reasonable
    assert len(violations) == 0
    
    # 6. Enhanced Alpha Performance (with execution costs)
    from qmtl.runtime.transforms.alpha_performance import alpha_performance_node
    
    raw_returns = [0.02, 0.01, -0.005, 0.015, -0.01]
    
    # Test basic performance calculation
    basic_performance = alpha_performance_node(raw_returns, transaction_cost=0.001)
    assert "sharpe" in basic_performance
    assert "max_drawdown" in basic_performance
    
    # Test with realistic execution modeling
    execution_fills = [fill]  # Use the fill from earlier
    enhanced_performance = alpha_performance_node(
        raw_returns, 
        use_realistic_costs=True, 
        execution_fills=execution_fills
    )
    
    assert "sharpe" in enhanced_performance
    assert "execution_total_trades" in enhanced_performance
    assert enhanced_performance["execution_total_trades"] == 1
    
    print("✅ All backtest accuracy enhancements working correctly!")


def test_strategy_integration_with_validation():
    """Test strategy integration with validation enabled."""
    
    class EnhancedTestStrategy(Strategy):
        def setup(self):
            stream = StreamInput(interval="60s", period=10)
            stream.name = "price_stream"
            self.add_nodes([stream])
    
    strategy = EnhancedTestStrategy()
    strategy.setup()
    
    # Add clean weekday data
    for node in strategy.nodes:
        if isinstance(node, StreamInput):
            # Add valid weekday data
            weekday_ts = int(datetime(2024, 1, 3, 10, 0, tzinfo=timezone.utc).timestamp() * 1000)
            node.cache.append("test_queue", 60, weekday_ts, {"close": 100.0, "volume": 10000})
            
            weekday_ts2 = int(datetime(2024, 1, 3, 11, 0, tzinfo=timezone.utc).timestamp() * 1000)
            node.cache.append("test_queue", 60, weekday_ts2, {"close": 101.0, "volume": 12000})
    
    # Test data validation
    from qmtl.runtime.sdk.backtest_validation import validate_backtest_data
    reports = validate_backtest_data(strategy)
    
    # Should have good quality data
    for node_name, report in reports.items():
        assert report.data_quality_score >= 0.8
    
    # Test timing validation
    from qmtl.runtime.sdk.timing_controls import validate_backtest_timing
    timing_issues = validate_backtest_timing(strategy)
    
    # Should have no timing issues for weekday data
    assert len(timing_issues) == 0
    
    print("✅ Strategy integration with validation working correctly!")


def test_performance_with_realistic_costs():
    """Test performance calculation with realistic execution costs."""
    
    from qmtl.runtime.sdk.execution_modeling import ExecutionFill, OrderSide
    from qmtl.runtime.transforms.alpha_performance import (
        calculate_execution_metrics,
        adjust_returns_for_costs,
    )
    
    # Create sample execution fills
    fills = [
        ExecutionFill("1", "AAPL", OrderSide.BUY, 100, 100.0, 100.05, 1000, 2.0, 0.03, 0.02),
        ExecutionFill("2", "AAPL", OrderSide.SELL, 100, 99.0, 98.97, 2000, 2.0, -0.02, 0.01),
        ExecutionFill("3", "TSLA", OrderSide.BUY, 50, 200.0, 200.1, 3000, 1.5, 0.08, 0.02),
    ]
    
    metrics = calculate_execution_metrics(fills)
    
    assert metrics["total_trades"] == 3
    assert metrics["total_volume"] == 250  # 100 + 100 + 50
    assert metrics["total_commission"] == 5.5  # 2.0 + 2.0 + 1.5
    assert metrics["avg_commission_bps"] > 0
    assert metrics["total_execution_cost"] > 0
    
    # Test return adjustment
    raw_returns = [0.02, 0.01, -0.01, 0.03]
    adjusted_returns = adjust_returns_for_costs(raw_returns, fills)
    
    # Adjusted returns should be lower due to costs
    for raw, adj in zip(raw_returns, adjusted_returns):
        assert adj <= raw  # Costs reduce returns
    
    print("✅ Performance calculation with realistic costs working correctly!")


def test_risk_aware_position_sizing():
    """Test risk-aware position sizing workflow."""
    
    risk_manager = RiskManager(
        max_leverage=2.0,
        position_size_limit_pct=0.10,
        enable_dynamic_sizing=True
    )
    
    portfolio_value = 100000
    
    # Test position sizing for different volatility assets
    conservative_size = risk_manager.calculate_position_size(
        symbol="BOND",
        target_allocation_pct=0.10,
        current_price=100.0,
        portfolio_value=portfolio_value,
        current_volatility=0.05  # Low volatility
    )
    
    aggressive_size = risk_manager.calculate_position_size(
        symbol="CRYPTO",
        target_allocation_pct=0.10,
        current_price=100.0,
        portfolio_value=portfolio_value,
        current_volatility=0.50  # High volatility
    )
    
    # High volatility asset should get smaller position size
    assert aggressive_size < conservative_size
    assert aggressive_size > 0  # But still positive
    
    # Test validation with portfolio constraints
    large_position_size = 200  # $20k position = 20% of portfolio
    
    is_valid, violation, adjusted = risk_manager.validate_position_size(
        symbol="LARGE_POS",
        proposed_quantity=large_position_size,
        current_price=100.0,
        portfolio_value=portfolio_value,
        current_positions={}
    )
    
    # Should violate 10% position limit
    assert not is_valid
    assert violation is not None
    assert adjusted == 100  # Should be adjusted to 10% = $10k / $100 = 100 shares
    
    print("✅ Risk-aware position sizing working correctly!")


if __name__ == "__main__":
    test_comprehensive_backtest_accuracy_enhancements()
    test_strategy_integration_with_validation()
    test_performance_with_realistic_costs()
    test_risk_aware_position_sizing()
    print("\n🎉 All comprehensive integration tests passed!")
    print("✅ Enhanced backtest execution accuracy features are working correctly!")

