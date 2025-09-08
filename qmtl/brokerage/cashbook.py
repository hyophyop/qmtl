"""Multi-currency cashbook data structures.

Provides minimal utilities to track settled and unsettled cash balances
across multiple currencies along with simple exchange rates for valuing
positions in a base currency.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


@dataclass
class CashEntry:
    """Cash position for a single currency."""

    balance: float = 0.0
    pending: float = 0.0  # positive credit, negative debit waiting to settle
    rate: float = 1.0  # conversion rate to the account base currency


class Cashbook:
    """Simple mapping of currency codes to :class:`CashEntry` instances."""

    def __init__(self) -> None:
        self._entries: Dict[str, CashEntry] = {}

    def _entry(self, currency: str) -> CashEntry:
        return self._entries.setdefault(currency, CashEntry())

    def set(self, currency: str, balance: float, rate: float = 1.0) -> None:
        entry = self._entry(currency)
        entry.balance = balance
        entry.rate = rate

    def adjust(self, currency: str, amount: float) -> None:
        self._entry(currency).balance += amount

    def reserve(self, currency: str, amount: float) -> None:
        self._entry(currency).pending += amount

    def release(self, currency: str, amount: float) -> None:
        self._entry(currency).pending -= amount

    def get(self, currency: str) -> CashEntry:
        return self._entry(currency)

    def total_value(self, base_currency: str) -> float:
        """Return total cash value converted to ``base_currency`` using rates."""
        total = 0.0
        for cur, entry in self._entries.items():
            if cur == base_currency:
                total += entry.balance + entry.pending
            else:
                total += (entry.balance + entry.pending) * entry.rate
        return total
