from datetime import datetime, time, timezone

from qmtl.sdk.timing_controls import MarketHours, MarketSession, TimingController


def test_dst_boundary_does_not_break_session_detection():
    # Use typical US hours; timestamps around a DST change Sunday should be CLOSED
    hours = MarketHours(
        pre_market_start=time(4, 0),
        regular_start=time(9, 30),
        regular_end=time(16, 0),
        post_market_end=time(20, 0),
    )
    ctrl = TimingController(market_hours=hours)

    # Sunday before DST change
    t1 = datetime(2024, 3, 10, 5, 0, tzinfo=timezone.utc)  # Sunday
    ok, _, sess = ctrl.validate_timing(t1)
    assert not ok and sess == MarketSession.CLOSED

    # Monday after DST change (still considered regular day)
    t2 = datetime(2024, 3, 11, 14, 0, tzinfo=timezone.utc)  # Monday
    ok, _, sess = ctrl.validate_timing(t2)
    assert sess in {
        MarketSession.PRE_MARKET,
        MarketSession.REGULAR,
        MarketSession.POST_MARKET,
    }


def test_early_close_behaves_as_post_market_after_cutoff():
    # Simulate early close by setting regular_end earlier
    hours = MarketHours(
        pre_market_start=time(4, 0),
        regular_start=time(9, 30),
        regular_end=time(13, 0),  # early close
        post_market_end=time(17, 0),
    )
    ctrl = TimingController(market_hours=hours, require_regular_hours=True)

    # At 14:00 on a weekday, order should be rejected as post-market under early close
    t = datetime(2024, 1, 3, 14, 0, tzinfo=timezone.utc)  # Wednesday
    ok, _, sess = ctrl.validate_timing(t)
    assert not ok and sess == MarketSession.POST_MARKET


def test_lunch_break_results_in_closed_session():
    hours = MarketHours(
        pre_market_start=time(4, 0),
        regular_start=time(9, 30),
        regular_end=time(16, 0),
        post_market_end=time(20, 0),
        lunch_start=time(11, 30),
        lunch_end=time(12, 30),
    )
    ctrl = TimingController(market_hours=hours)

    t = datetime(2024, 1, 3, 12, 0, tzinfo=timezone.utc)  # Wednesday
    ok, _, sess = ctrl.validate_timing(t)
    assert not ok and sess == MarketSession.LUNCH
