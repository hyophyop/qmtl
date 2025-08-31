"""Exchange hours provider backed by SDK timing controls."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from qmtl.sdk.timing_controls import MarketHours, MarketSession


@dataclass
class ExchangeHoursProvider:
    """Simple provider to answer market session queries."""

    market_hours: MarketHours = MarketHours()
    allow_pre_post_market: bool = False
    require_regular_hours: bool = False

    def session(self, ts: datetime) -> MarketSession:
        return self.market_hours.get_session(ts)

    def is_open(self, ts: datetime) -> bool:
        session = self.session(ts)
        if session == MarketSession.CLOSED:
            return False
        if self.require_regular_hours and session != MarketSession.REGULAR:
            return False
        if not self.allow_pre_post_market and session in {MarketSession.PRE_MARKET, MarketSession.POST_MARKET}:
            return False
        return True

