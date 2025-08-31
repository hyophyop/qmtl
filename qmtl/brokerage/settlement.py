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

    def __init__(self, days: int = 2) -> None:
        self.days = days
        self._pending: List[PendingSettlement] = []

    def record(self, fill: Fill, now: datetime) -> None:
        notional = fill.price * fill.quantity
        # Cash effect sign mirrors BrokerageModel immediate move; record for audit
        self._pending.append(
            PendingSettlement(symbol=fill.symbol, amount=notional, settles_at=now + timedelta(days=self.days))
        )

    def apply_due(self, account: Account, now: datetime) -> int:
        """Apply all settlements due at or before `now`. Returns count applied."""
        remaining: List[PendingSettlement] = []
        applied = 0
        for p in self._pending:
            if p.settles_at <= now:
                # No-op in this minimal model, since BrokerageModel already moved cash
                applied += 1
            else:
                remaining.append(p)
        self._pending = remaining
        return applied

