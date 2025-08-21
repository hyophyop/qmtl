from qmtl.examples.strategies.risk_managed_strategy import enforce_position_limit
from qmtl.sdk.risk_management import RiskViolationType


def test_violation_detected_when_exceeding_limit() -> None:
    is_valid, violation, adjusted = enforce_position_limit(
        symbol="AAPL", proposed_quantity=20, price=10.0, portfolio_value=1_000.0
    )
    assert not is_valid
    assert violation is not None
    assert violation.violation_type == RiskViolationType.POSITION_SIZE_LIMIT
    assert adjusted == 10.0


def test_no_violation_within_limit() -> None:
    is_valid, violation, adjusted = enforce_position_limit(
        symbol="AAPL", proposed_quantity=5, price=10.0, portfolio_value=1_000.0
    )
    assert is_valid
    assert violation is None
    assert adjusted == 5
