import pytest

from qmtl.sdk.risk_management import RiskManager, RiskViolationType


@pytest.mark.parametrize(
    "config, proposed_quantity, expected",
    [
        pytest.param(
            dict(max_position_size=10000, position_size_limit_pct=0.10),
            50,
            dict(is_valid=True, violation_type=None, adjusted=50),
            id="within-limits",
        ),
        pytest.param(
            dict(max_position_size=5000, enable_dynamic_sizing=True),
            100,
            dict(is_valid=False, violation_type=RiskViolationType.POSITION_SIZE_LIMIT, adjusted=50),
            id="absolute-limit",
        ),
        pytest.param(
            dict(position_size_limit_pct=0.05, enable_dynamic_sizing=True),
            80,
            dict(is_valid=False, violation_type=RiskViolationType.POSITION_SIZE_LIMIT, adjusted=50),
            id="percentage-limit",
        ),
        pytest.param(
            dict(max_position_size=5000, enable_dynamic_sizing=False),
            100,
            dict(is_valid=False, violation_type=RiskViolationType.POSITION_SIZE_LIMIT, adjusted=0.0),
            id="no-dynamic-sizing",
        ),
    ],
)
def test_validate_position_size_cases(config, proposed_quantity, expected):
    risk_manager = RiskManager(**config)

    is_valid, violation, adjusted_quantity = risk_manager.validate_position_size(
        symbol="AAPL",
        proposed_quantity=proposed_quantity,
        current_price=100.0,
        portfolio_value=100000,
        current_positions={},
    )

    assert is_valid is expected["is_valid"]
    if expected["violation_type"] is None:
        assert violation is None
    else:
        assert violation is not None
        assert violation.violation_type == expected["violation_type"]
    assert adjusted_quantity == pytest.approx(expected["adjusted"])
