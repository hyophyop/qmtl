"""Unit tests for composable risk controls."""

from __future__ import annotations

import pytest

from qmtl.sdk.risk.controls import (
    DrawdownControl,
    VolatilityControl,
    evaluate_concentration,
    evaluate_leverage,
    evaluate_position_size,
)
from qmtl.sdk.risk.models import PositionInfo, RiskViolationType


@pytest.fixture
def sample_positions() -> dict[str, PositionInfo]:
    return {
        "AAPL": PositionInfo("AAPL", 100, 10000, 0, 100, 100),
        "TSLA": PositionInfo("TSLA", 50, 7500, 0, 150, 150),
    }


def test_position_size_evaluator_absolute_limit(sample_positions):
    is_valid, violation, adjusted = evaluate_position_size(
        symbol="AAPL",
        proposed_quantity=200,
        current_price=100.0,
        portfolio_value=150000,
        current_positions=sample_positions,
        max_position_size=15000,
        position_size_limit_pct=0.20,
        enable_dynamic_sizing=True,
    )

    assert not is_valid
    assert violation is not None
    assert violation.violation_type == RiskViolationType.POSITION_SIZE_LIMIT
    assert adjusted == pytest.approx(150)


def test_position_size_evaluator_percentage_limit(sample_positions):
    is_valid, violation, adjusted = evaluate_position_size(
        symbol="TSLA",
        proposed_quantity=200,
        current_price=150.0,
        portfolio_value=100000,
        current_positions=sample_positions,
        max_position_size=None,
        position_size_limit_pct=0.10,
        enable_dynamic_sizing=True,
    )

    assert not is_valid
    assert violation is not None
    assert violation.current_value == pytest.approx(0.30)
    assert adjusted == pytest.approx((100000 * 0.10) / 150.0)


def test_position_size_evaluator_no_dynamic(sample_positions):
    is_valid, violation, adjusted = evaluate_position_size(
        symbol="AAPL",
        proposed_quantity=200,
        current_price=100.0,
        portfolio_value=100000,
        current_positions=sample_positions,
        max_position_size=5000,
        position_size_limit_pct=0.20,
        enable_dynamic_sizing=False,
    )

    assert not is_valid
    assert violation is not None
    assert adjusted == 0.0


def test_leverage_evaluator(sample_positions):
    total_exposure = sum(pos.exposure for pos in sample_positions.values())
    violation = evaluate_leverage(
        total_exposure,
        portfolio_value=10000,
        max_leverage=1.5,
        timestamp=1,
    )

    assert violation is not None
    assert violation.violation_type == RiskViolationType.LEVERAGE_LIMIT
    assert violation.current_value == pytest.approx(total_exposure / 10000)


def test_concentration_evaluator(sample_positions):
    violations = evaluate_concentration(
        sample_positions,
        portfolio_value=15000,
        max_concentration_pct=0.40,
        timestamp=1,
    )

    assert violations
    symbols = {v.symbol for v in violations}
    assert symbols == {"AAPL", "TSLA"}


def test_drawdown_control_violation():
    control = DrawdownControl(max_drawdown_pct=0.10)

    assert not control.update(portfolio_value=100000, timestamp=0)
    violations = control.update(portfolio_value=85000, timestamp=1)

    assert violations
    assert violations[0].violation_type == RiskViolationType.DRAWDOWN_LIMIT
    assert control.current_drawdown == pytest.approx(0.15)


def test_volatility_control_violation():
    control = VolatilityControl(
        max_portfolio_volatility=0.15,
        lookback=30,
        min_samples=5,
    )

    base = 100000
    for idx in range(10):
        shock = 1.05 if idx % 2 == 0 else 0.95
        value = base * shock
        violations = control.update(timestamp=idx, portfolio_value=value)

    assert violations
    assert violations[0].violation_type == RiskViolationType.VOLATILITY_LIMIT
    assert violations[0].current_value > 0.15


