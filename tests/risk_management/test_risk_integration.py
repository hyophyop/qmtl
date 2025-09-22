import pytest

from qmtl.sdk.risk_management import PositionInfo, RiskManager


def test_integration_risk_workflow():
    risk_manager = RiskManager(
        max_leverage=2.0,
        max_concentration_pct=0.25,
        position_size_limit_pct=0.10,
        max_drawdown_pct=0.15,
    )

    position_size = risk_manager.calculate_position_size(
        symbol="AAPL",
        target_allocation_pct=0.08,
        current_price=150.0,
        portfolio_value=100000,
    )
    assert abs(position_size - 53.33) < 0.1

    is_valid, violation, adjusted = risk_manager.validate_position_size(
        symbol="AAPL",
        proposed_quantity=position_size,
        current_price=150.0,
        portfolio_value=100000,
        current_positions={},
    )
    assert is_valid
    assert violation is None
    assert adjusted == pytest.approx(position_size)

    positions = {
        "AAPL": PositionInfo("AAPL", position_size, position_size * 150, 0, 150, 150),
        "TSLA": PositionInfo("TSLA", 20, 20 * 200, 0, 200, 200),
    }

    violations = risk_manager.validate_portfolio_risk(
        positions=positions,
        portfolio_value=100000,
        timestamp=1000,
    )
    assert not violations

    summary = risk_manager.get_risk_summary()
    assert summary["total_violations"] == 0
    assert summary["peak_portfolio_value"] == 100000
