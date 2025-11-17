"""Margin interest model."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Tuple, TYPE_CHECKING, Union

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .cashbook import Cashbook

RateTiers = Iterable[Tuple[float, float]]


@dataclass
class MarginInterestModel:
    """Daily interest calculator supporting tiered rates.

    ``cash_rate`` and ``borrow_rate`` may be specified as a single float or an
    iterable of ``(threshold, rate)`` tuples. Thresholds represent balance
    amounts at which the accompanying rate begins to apply. For example:

    ``[(0, 0.01), (10_000, 0.02)]`` applies a 1% rate up to 10k and 2% above.

    Rates are annual; calculation assumes a 365-day convention.
    """

    cash_rate: Union[float, RateTiers] = 0.0
    borrow_rate: Union[float, RateTiers] = 0.05

    def _resolve_rate(self, tiers: Union[float, RateTiers], amount: float) -> float:
        if isinstance(tiers, (int, float)):
            return float(tiers)
        rate = 0.0
        for threshold, r in sorted(tiers):
            if amount >= threshold:
                rate = r
            else:
                break
        return rate

    def rate_for(self, balance: float) -> float:
        amt = abs(balance)
        return self._resolve_rate(self.cash_rate, amt) if balance >= 0 else self._resolve_rate(self.borrow_rate, amt)

    def daily_interest(self, balance: float, now: datetime) -> float:  # noqa: ARG002
        rate = self.rate_for(balance)
        return balance * (rate / 365.0)

    def accrue_daily(self, cashbook: "Cashbook", currency: str, now: datetime) -> float:
        balance = cashbook.get(currency).balance
        interest = self.daily_interest(balance, now)
        if interest:
            cashbook.adjust(currency, interest)
        return interest
