from datetime import datetime, date, time

from qmtl.brokerage import ExchangeHoursProvider


def test_holiday_closure_and_early_close():
    eh = ExchangeHoursProvider.with_us_sample_holidays(require_regular_hours=True)
    # Holiday full day
    d = date(2024, 12, 25)
    assert not eh.is_open(datetime.combine(d, time(10, 0)))
    # Early close day after Thanksgiving
    d2 = date(2024, 11, 29)
    assert eh.is_open(datetime.combine(d2, time(10, 0)))
    assert not eh.is_open(datetime.combine(d2, time(14, 0)))

