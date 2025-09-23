import pytest

from qmtl.runtime.sdk.execution_modeling import ExecutionFill, OrderSide
from qmtl.runtime.transforms.alpha_performance import (
    adjust_returns_for_costs,
    calculate_execution_metrics,
)


def test_execution_fill_properties():
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
        market_impact=0.02,
    )

    assert fill.total_cost == pytest.approx(10.0)
    assert fill.execution_shortfall == pytest.approx(0.1)


def test_execution_metrics_calculation():
    fills = [
        ExecutionFill("1", "AAPL", OrderSide.BUY, 100, 100.0, 100.05, 1000, 2.0, 0.03, 0.02),
        ExecutionFill("2", "AAPL", OrderSide.SELL, 100, 99.0, 98.97, 1100, 2.0, -0.02, 0.01),
        ExecutionFill("3", "MSFT", OrderSide.BUY, 50, 200.0, 200.1, 1200, 1.5, 0.08, 0.02),
    ]

    metrics = calculate_execution_metrics(fills)

    assert metrics["total_trades"] == 3
    assert metrics["total_volume"] == 250
    assert metrics["total_commission"] == 5.5
    assert metrics["avg_commission_bps"] > 0
    assert metrics["avg_slippage_bps"] > 0
    assert metrics["total_execution_cost"] > 0


def test_return_adjustment_for_costs():
    fill = ExecutionFill("1", "AAPL", OrderSide.BUY, 100, 100.0, 100.1, 1000, 5.0, 0.05, 0.02)

    raw_returns = [0.02, 0.01, -0.01, 0.03]
    adjusted_returns = adjust_returns_for_costs(raw_returns, [fill])

    assert len(adjusted_returns) == len(raw_returns)
    assert all(adj < raw for raw, adj in zip(raw_returns, adjusted_returns))


def test_empty_execution_history():
    metrics = calculate_execution_metrics([])
    assert metrics == {}

    raw_returns = [0.02, 0.01, -0.01]
    adjusted_returns = adjust_returns_for_costs(raw_returns, [])
    assert adjusted_returns == raw_returns
