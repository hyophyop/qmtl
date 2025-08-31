"""Margin interest model."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class MarginInterestModel:
    """Simple daily interest calculator for borrow/cash balances.

    Positive balances accrue at `cash_rate`; negative balances incur `borrow_rate`.
    Rates are annual; calculation assumes 365-day convention.
    """

    cash_rate: float = 0.0
    borrow_rate: float = 0.05

    def daily_interest(self, balance: float, now: datetime) -> float:
        rate = self.cash_rate if balance >= 0 else -self.borrow_rate
        return balance * (rate / 365.0)

