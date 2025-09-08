from datetime import datetime, timezone

import pytest

from qmtl.brokerage import Cashbook, MarginInterestModel


def test_margin_interest_daily_accrual():
    m = MarginInterestModel(cash_rate=0.01, borrow_rate=0.10)
    now = datetime.now(timezone.utc)
    # Positive cash accrues
    assert m.daily_interest(1000.0, now) == pytest.approx(1000.0 * (0.01 / 365.0))
    # Negative balance incurs cost
    assert m.daily_interest(-2000.0, now) == pytest.approx(-2000.0 * (0.10 / 365.0))


def test_margin_interest_tiered_rates():
    m = MarginInterestModel(
        cash_rate=[(0, 0.01), (10_000, 0.02)],
        borrow_rate=[(0, 0.10), (5_000, 0.08)],
    )
    now = datetime.now(timezone.utc)
    assert m.daily_interest(5_000.0, now) == pytest.approx(5_000.0 * (0.01 / 365.0))
    assert m.daily_interest(20_000.0, now) == pytest.approx(20_000.0 * (0.02 / 365.0))
    assert m.daily_interest(-1_000.0, now) == pytest.approx(-1_000.0 * (0.10 / 365.0))
    assert m.daily_interest(-10_000.0, now) == pytest.approx(-10_000.0 * (0.08 / 365.0))


def test_margin_interest_cashbook_accrual():
    m = MarginInterestModel(cash_rate=0.01, borrow_rate=0.10)
    cb = Cashbook()
    cb.set("USD", 1_000.0)
    now = datetime.now(timezone.utc)
    interest = m.accrue_daily(cb, "USD", now)
    assert interest == pytest.approx(1_000.0 * (0.01 / 365.0))
    assert cb.get("USD").balance == pytest.approx(1_000.0 + interest)
    cb.set("USD", -2_000.0)
    interest = m.accrue_daily(cb, "USD", now)
    assert interest == pytest.approx(-2_000.0 * (0.10 / 365.0))
    assert cb.get("USD").balance == pytest.approx(-2_000.0 + interest)

