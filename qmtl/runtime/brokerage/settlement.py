"""Settlement model and cashbook-aware utilities."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, date
from typing import Dict, List, Set

from .order import Fill, Account


@dataclass
class PendingSettlement:
    symbol: str
    currency: str
    amount: float  # positive -> credit, negative -> debit
    settles_at: datetime


class SettlementModel:
    """T+N settlement queue with optional cash deferral and holiday awareness."""

    def __init__(
        self,
        days: int = 2,
        defer_cash: bool = False,
        holidays: Set[date] | None = None,
    ) -> None:
        self.days = days
        self.defer_cash = defer_cash
        self.holidays: Set[date] = holidays or set()
        self._pending: List[PendingSettlement] = []
        self._reserved: Dict[str, float] = {}

    # -- internal utilities -------------------------------------------------
    def _add_business_days(self, start: datetime, days: int) -> datetime:
        current = start
        remaining = days
        while remaining > 0:
            current += timedelta(days=1)
            if current.weekday() >= 5 or current.date() in self.holidays:
                continue
            remaining -= 1
        return current

    # -- recording and applying settlements --------------------------------
    def record(self, account: Account, fill: Fill, currency: str, now: datetime) -> None:
        """Record a fill for future settlement."""

        cost = -(fill.price * fill.quantity + getattr(fill, "fee", 0.0))
        settles = self._add_business_days(now, self.days)
        self._pending.append(
            PendingSettlement(
                symbol=fill.symbol,
                currency=currency,
                amount=cost,
                settles_at=settles,
            )
        )
        if self.defer_cash:
            account.cashbook.reserve(currency, cost)
            if cost < 0:  # buy, reserve cash
                self._reserved[currency] = self._reserved.get(currency, 0.0) + (-cost)

    def apply_due(self, account: Account, now: datetime) -> int:
        """Apply all settlements due at or before ``now``. Returns count applied."""

        remaining: List[PendingSettlement] = []
        applied = 0
        for p in self._pending:
            if p.settles_at <= now:
                if self.defer_cash:
                    account.cashbook.adjust(p.currency, p.amount)
                    account.cashbook.release(p.currency, p.amount)
                    if p.amount < 0:
                        self._reserved[p.currency] = self._reserved.get(p.currency, 0.0) + p.amount
                applied += 1
            else:
                remaining.append(p)
        self._pending = remaining
        # cleanup near-zero reserved values
        for k, v in list(self._reserved.items()):
            if abs(v) < 1e-9:
                del self._reserved[k]
        return applied

    # -- utilities for buying power ---------------------------------------
    def reserved_for(self, currency: str) -> float:
        return max(0.0, self._reserved.get(currency, 0.0))

    @property
    def reserved(self) -> float:
        return sum(max(v, 0.0) for v in self._reserved.values())

    def available_cash(self, account: Account, currency: str) -> float:
        return account.cashbook.get(currency).balance - self.reserved_for(currency)
