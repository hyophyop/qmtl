"""Exchange hours provider backed by SDK timing controls."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, date, time
from typing import Set, Dict

from functools import lru_cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from qmtl.runtime.sdk.timing_controls import MarketHours, MarketSession


@lru_cache(maxsize=1)
def _timing_controls():
    from qmtl.runtime.sdk.timing_controls import MarketHours as _MarketHours, MarketSession as _MarketSession

    return _MarketHours, _MarketSession


def _default_market_hours():
    MarketHours, _ = _timing_controls()
    return MarketHours(
        pre_market_start=time(4, 0),
        regular_start=time(9, 30),
        regular_end=time(16, 0),
        post_market_end=time(20, 0),
    )


@dataclass
class ExchangeHoursProvider:
    """Simple provider to answer market session queries."""

    market_hours: "MarketHours" = field(default_factory=_default_market_hours)
    allow_pre_post_market: bool = False
    require_regular_hours: bool = False
    holidays: Set[date] = field(default_factory=set)
    early_closes: Dict[date, time] = field(default_factory=dict)

    def session(self, ts: datetime) -> "MarketSession":
        # Holiday full-day closure
        if self.holidays and ts.date() in self.holidays:
            return _timing_controls()[1].CLOSED
        # Early close handling: if provided and ts is after early close, treat as closed
        if self.early_closes:
            cl = self.early_closes.get(ts.date())
            if cl and ts.time() >= cl:
                return _timing_controls()[1].CLOSED
        return self.market_hours.get_session(ts)

    def is_open(self, ts: datetime) -> bool:
        session = self.session(ts)
        market_session = _timing_controls()[1]
        if session == market_session.CLOSED:
            return False
        if self.require_regular_hours and session != market_session.REGULAR:
            return False
        if not self.allow_pre_post_market and session in {market_session.PRE_MARKET, market_session.POST_MARKET}:
            return False
        return True

    @staticmethod
    def with_us_sample_holidays(*, allow_pre_post_market: bool = False, require_regular_hours: bool = False) -> "ExchangeHoursProvider":
        """Create a provider with a minimal set of US equity holidays and sample early closes.

        Note: This is a compact sample for testing/demo purposes, not an exhaustive calendar.
        """
        from datetime import date, time
        holidays = {
            date(2024, 1, 1),   # New Year's Day
            date(2024, 7, 4),   # Independence Day
            date(2024, 12, 25), # Christmas Day
        }
        early = {
            date(2024, 11, 29): time(13, 0),  # Day after Thanksgiving early close
        }
        return ExchangeHoursProvider(
            allow_pre_post_market=allow_pre_post_market,
            require_regular_hours=require_regular_hours,
            holidays=holidays,
            early_closes=early,
        )
