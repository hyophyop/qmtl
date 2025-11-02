import pytest

from qmtl.runtime.sdk.risk_management import PositionInfo, RiskViolation, RiskViolationType


def test_position_info_exposure():
    long_position = PositionInfo(
        symbol="AAPL",
        quantity=100,
        market_value=10000,
        unrealized_pnl=500,
        entry_price=95.0,
        current_price=100.0,
    )
    short_position = PositionInfo(
        symbol="TSLA",
        quantity=-50,
        market_value=-5000,
        unrealized_pnl=-200,
        entry_price=110.0,
        current_price=100.0,
    )

    assert long_position.exposure == 10000
    assert short_position.exposure == 5000


@pytest.mark.parametrize(
    "current, limit, expected",
    [
        pytest.param(110, 100, "low", id="low"),
        pytest.param(130, 100, "medium", id="medium"),
        pytest.param(180, 100, "high", id="high"),
        pytest.param(250, 100, "critical", id="critical"),
    ],
)
def test_risk_violation_severity(current, limit, expected):
    violation = RiskViolation(
        violation_type=RiskViolationType.POSITION_SIZE_LIMIT,
        current_value=current,
        limit_value=limit,
        description="Test",
        timestamp=1000,
    )

    assert violation.severity == expected
