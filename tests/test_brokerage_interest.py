from datetime import datetime, timezone

from qmtl.brokerage import MarginInterestModel


def test_margin_interest_daily_accrual():
    m = MarginInterestModel(cash_rate=0.01, borrow_rate=0.10)
    now = datetime.now(timezone.utc)
    # Positive cash accrues
    assert m.daily_interest(1000.0, now) == 1000.0 * (0.01 / 365.0)
    # Negative balance incurs cost
    assert m.daily_interest(-2000.0, now) == -2000.0 * (0.10 / 365.0)

