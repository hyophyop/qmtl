from __future__ import annotations

from datetime import datetime, timezone

import pytest

from qmtl.runtime.sdk.backtest_validation import BacktestDataValidator
from qmtl.runtime.sdk.execution_modeling import (
    ExecutionFill,
    ExecutionModel,
    OrderSide,
    OrderType,
    create_market_data_from_ohlcv,
)
from qmtl.runtime.sdk.risk_management import PositionInfo, RiskManager
from qmtl.runtime.sdk.timing_controls import TimingController
from qmtl.runtime.transforms.alpha_performance import (
    alpha_performance_node,
    calculate_execution_metrics,
    adjust_returns_for_costs,
)


def test_backtest_validator_scores_clean_series_as_perfect() -> None:
    validator = BacktestDataValidator(
        max_price_change_pct=0.05,
        min_price=1.0,
        max_gap_tolerance_sec=120,
        required_fields=["close", "volume"],
    )

    clean_data = [
        (1_000, {"close": 100.0, "volume": 10_000}),
        (1_060, {"close": 102.0, "volume": 11_000}),
        (1_120, {"close": 101.0, "volume": 9_500}),
    ]

    report = validator.validate_time_series(clean_data, interval_sec=60)

    assert report.data_quality_score == 1.0
    assert not report.has_issues


def test_execution_model_applies_commission_and_slippage() -> None:
    model = ExecutionModel(
        commission_rate=0.001,
        commission_minimum=1.0,
        base_slippage_bps=2.0,
        market_impact_coeff=0.1,
    )
    market_data = create_market_data_from_ohlcv(
        timestamp=1_000,
        open_price=100.0,
        high=102.0,
        low=99.0,
        close=101.0,
        volume=50_000,
    )

    fill = model.simulate_execution(
        order_id="abc",
        symbol="AAPL",
        side=OrderSide.BUY,
        quantity=100,
        order_type=OrderType.MARKET,
        requested_price=101.0,
        market_data=market_data,
        timestamp=1_000,
    )

    assert fill.quantity == 100
    assert fill.commission >= 1.0
    assert fill.fill_price > market_data.ask
    assert fill.total_cost > 0


def test_timing_controller_requires_regular_session() -> None:
    controller = TimingController(
        allow_pre_post_market=False,
        require_regular_hours=True,
    )

    weekday = datetime(2024, 1, 3, 10, 30, tzinfo=timezone.utc)
    weekend = datetime(2024, 1, 6, 10, 30, tzinfo=timezone.utc)

    is_valid, _, _ = controller.validate_timing(weekday)
    assert is_valid

    is_valid, reason, _ = controller.validate_timing(weekend)
    assert not is_valid
    assert reason


def test_risk_manager_enforces_position_limits() -> None:
    risk_manager = RiskManager(
        max_leverage=2.0,
        max_concentration_pct=0.25,
        position_size_limit_pct=0.10,
        max_drawdown_pct=0.15,
    )

    position_size = risk_manager.calculate_position_size(
        symbol="AAPL",
        target_allocation_pct=0.08,
        current_price=101.0,
        portfolio_value=100_000,
    )
    assert 70 < position_size < 80

    is_valid, violation, adjusted = risk_manager.validate_position_size(
        symbol="AAPL",
        proposed_quantity=position_size * 3,  # deliberately too large
        current_price=101.0,
        portfolio_value=100_000,
        current_positions={},
    )

    assert not is_valid
    assert violation is not None
    expected_cap = (100_000 * 0.10) / 101.0
    assert adjusted < position_size * 3
    assert adjusted == pytest.approx(expected_cap)

    positions = {
        "AAPL": PositionInfo("AAPL", position_size, position_size * 101.0, 0, 101.0, 101.0),
    }
    violations = risk_manager.validate_portfolio_risk(
        positions=positions,
        portfolio_value=100_000,
        timestamp=1_000,
    )
    assert not violations


def test_alpha_performance_includes_execution_metrics() -> None:
    raw_returns = [0.02, 0.01, -0.005, 0.015, -0.01]
    fills = [
        ExecutionFill("1", "AAPL", OrderSide.BUY, 100, 100.0, 100.05, 1_000, 2.0, 0.03, 0.02),
    ]

    result = alpha_performance_node(
        raw_returns,
        use_realistic_costs=True,
        execution_fills=fills,
    )

    assert "execution_total_trades" in result
    assert result["execution_total_trades"] == 1
    assert "alpha_performance.sharpe" in result

    adjusted_returns = adjust_returns_for_costs(raw_returns, fills)
    assert len(adjusted_returns) == len(raw_returns)
    for raw, adjusted in zip(raw_returns, adjusted_returns):
        assert adjusted <= raw


def test_execution_metrics_summarize_trading_activity() -> None:
    fills = [
        ExecutionFill("1", "AAPL", OrderSide.BUY, 100, 100.0, 100.05, 1_000, 2.0, 0.03, 0.02),
        ExecutionFill("2", "AAPL", OrderSide.SELL, 50, 101.0, 101.02, 500, 1.0, -0.01, 0.01),
    ]

    metrics = calculate_execution_metrics(fills)

    assert metrics["total_trades"] == 2
    assert metrics["total_volume"] == 150
    assert metrics["total_commission"] == pytest.approx(3.0)
