import pytest

from qmtl.sdk.risk_management import PositionInfo, RiskManager, RiskViolationType


def test_validate_portfolio_risk_leverage_violation(sample_positions):
    risk_manager = RiskManager(max_leverage=2.0)

    violations = risk_manager.validate_portfolio_risk(
        positions=sample_positions,
        portfolio_value=20000,
        timestamp=1000,
    )

    leverage_violations = [
        v for v in violations if v.violation_type == RiskViolationType.LEVERAGE_LIMIT
    ]
    assert leverage_violations
    assert leverage_violations[0].current_value == pytest.approx(3.0)
    assert leverage_violations[0].limit_value == 2.0


def test_validate_portfolio_risk_concentration_violation():
    risk_manager = RiskManager(max_concentration_pct=0.20)
    positions = {
        "AAPL": PositionInfo("AAPL", 300, 30000, 0, 100, 100),
        "TSLA": PositionInfo("TSLA", 100, 10000, 0, 100, 100),
    }

    violations = risk_manager.validate_portfolio_risk(
        positions=positions,
        portfolio_value=100000,
        timestamp=1000,
    )

    concentration_violations = [
        v for v in violations if v.violation_type == RiskViolationType.CONCENTRATION_LIMIT
    ]
    assert concentration_violations
    assert concentration_violations[0].symbol == "AAPL"
    assert concentration_violations[0].current_value == pytest.approx(0.30)
    assert concentration_violations[0].limit_value == 0.20


def test_validate_world_risk_concentration_violation():
    risk_manager = RiskManager(max_concentration_pct=0.40)

    strat_a_positions = {"AAPL": PositionInfo("AAPL", 100, 10000, 0, 100, 100)}
    strat_b_positions = {"AAPL": PositionInfo("AAPL", 100, 10000, 0, 100, 100)}

    violations = risk_manager.validate_world_risk(
        strategies=[
            (10000, strat_a_positions),
            (10000, strat_b_positions),
        ],
        timestamp=0,
    )

    concentration_violations = [
        v for v in violations if v.violation_type == RiskViolationType.CONCENTRATION_LIMIT
    ]
    assert concentration_violations
    assert concentration_violations[0].current_value == pytest.approx(1.0)
    assert concentration_violations[0].limit_value == 0.40


def test_validate_portfolio_risk_drawdown_violation():
    risk_manager = RiskManager(max_drawdown_pct=0.10)
    risk_manager.peak_portfolio_value = 100000

    positions = {
        "AAPL": PositionInfo("AAPL", 100, 10000, -5000, 100, 100),
    }

    violations = risk_manager.validate_portfolio_risk(
        positions=positions,
        portfolio_value=80000,
        timestamp=1000,
    )

    drawdown_violations = [
        v for v in violations if v.violation_type == RiskViolationType.DRAWDOWN_LIMIT
    ]
    assert drawdown_violations
    assert drawdown_violations[0].current_value == pytest.approx(0.20)
    assert drawdown_violations[0].limit_value == 0.10
