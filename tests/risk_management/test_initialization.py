from qmtl.sdk.risk_management import RiskManager


def test_default_initialization(default_risk_manager):
    assert default_risk_manager.max_leverage == 3.0
    assert default_risk_manager.max_drawdown_pct == 0.15
    assert default_risk_manager.max_concentration_pct == 0.20
    assert default_risk_manager.position_size_limit_pct == 0.10
    assert default_risk_manager.enable_dynamic_sizing is True
    assert default_risk_manager.max_position_size is None


def test_custom_initialization():
    risk_manager = RiskManager(
        max_position_size=50000,
        max_leverage=2.0,
        max_drawdown_pct=0.10,
        max_concentration_pct=0.15,
        position_size_limit_pct=0.05,
        enable_dynamic_sizing=False,
    )

    assert risk_manager.max_position_size == 50000
    assert risk_manager.max_leverage == 2.0
    assert risk_manager.max_drawdown_pct == 0.10
    assert risk_manager.max_concentration_pct == 0.15
    assert risk_manager.position_size_limit_pct == 0.05
    assert risk_manager.enable_dynamic_sizing is False
