import pytest

from qmtl.sdk.risk_management import RiskManager, RiskViolation, RiskViolationType


def test_get_risk_summary():
    risk_manager = RiskManager()
    risk_manager.violations = [
        RiskViolation(RiskViolationType.LEVERAGE_LIMIT, 3.0, 2.0, "Test", 1000),
        RiskViolation(RiskViolationType.POSITION_SIZE_LIMIT, 150, 100, "Test", 1000),
    ]
    risk_manager.peak_portfolio_value = 100000
    risk_manager.portfolio_value_history = [(1000, 100000), (2000, 90000)]

    summary = risk_manager.get_risk_summary()

    assert summary["total_violations"] == 2
    assert summary["violation_types"][RiskViolationType.LEVERAGE_LIMIT.value] == 1
    assert summary["violation_types"][RiskViolationType.POSITION_SIZE_LIMIT.value] == 1
    assert summary["peak_portfolio_value"] == 100000
    assert summary["current_drawdown"] == pytest.approx(0.1)
    assert "risk_config" in summary


def test_volatility_limit_validation():
    risk_manager = RiskManager(max_portfolio_volatility=0.15)
    base_value = 100000

    for i in range(35):
        value = base_value * 1.05 if i % 2 == 0 else base_value * 0.95
        risk_manager.portfolio_value_history.append((i * 1000, value))

    violations = risk_manager._check_volatility_limit(35000)

    volatility_violations = [
        v for v in violations if v.violation_type == RiskViolationType.VOLATILITY_LIMIT
    ]
    assert volatility_violations
    assert volatility_violations[0].current_value > 0.15
