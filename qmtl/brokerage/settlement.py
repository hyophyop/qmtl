"""Settlement model and minimal cashbook structures."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List

from .order import Fill, Account


@dataclass
class PendingSettlement:
    symbol: str
    amount: float  # positive -> credit, negative -> debit
    settles_at: datetime


class SettlementModel:
    """Minimal T+N settlement queue.

    Note: This implementation tracks pending settlements but does not alter
    the immediate cash movement performed in BrokerageModel. Integrators may
    choose to reserve cash instead and only apply at settle time.
    """

    def __init__(self, days: int = 2, defer_cash: bool = False) -> None:
        self.days = days
        self.defer_cash = defer_cash
        self._pending: List[PendingSettlement] = []
        self._reserved: float = 0.0  # reserved cash for pending buys (fees included)

    def record(self, fill: Fill, now: datetime) -> None:
        # Negative amount represents cash debit (buy); positive credit (sell)
        amount = -fill.price * fill.quantity
        self._pending.append(
            PendingSettlement(
                symbol=fill.symbol,
                amount=amount,
                settles_at=now + timedelta(days=self.days),
            )
        )
        # If deferring cash, reserve funds for buy orders (cash outflow)
        if self.defer_cash and fill.quantity > 0:
            self._reserved += (-amount) + getattr(fill, "fee", 0.0)

    def apply_due(self, account: Account, now: datetime) -> int:
        """Apply all settlements due at or before `now`. Returns count applied."""
        remaining: List[PendingSettlement] = []
        applied = 0
        for p in self._pending:
            if p.settles_at <= now:
                # Apply cash if in defer mode; otherwise this is a no-op
                if self.defer_cash:
                    account.cash += p.amount
                    # Reduce reserved for buys
                    if p.amount < 0:
                        self._reserved -= abs(p.amount)
                applied += 1
            else:
                remaining.append(p)
        self._pending = remaining
        return applied

    # Utilities for buying power
    @property
    def reserved(self) -> float:
        return max(0.0, self._reserved)

    def available_cash(self, account: Account) -> float:
        return account.cash - self.reserved
