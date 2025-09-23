"""Shortable provider interface and default implementation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional, Dict, Tuple, Mapping


class ShortableProvider:
    """Provides short availability for symbols."""

    def is_shortable(self, symbol: str, on: Optional[date] = None) -> bool:
        qty = self.available_qty(symbol, on)
        return qty is not None and qty > 0

    def available_qty(self, symbol: str, on: Optional[date] = None) -> Optional[int]:
        return None

    # Borrowing hooks -----------------------------------------------------
    def borrow(self, symbol: str, quantity: int, on: Optional[date] = None) -> float:
        """Reserve ``quantity`` shares for shorting and return borrow fee.

        Default implementation assumes unlimited availability and no fee.
        """
        return 0.0

    def return_qty(self, symbol: str, quantity: int, on: Optional[date] = None) -> None:
        """Release previously borrowed quantity back to the pool."""
        return None


@dataclass(frozen=True)
class ShortableLot:
    """Represents shortable quantity and borrow fee for a given day."""

    quantity: int
    fee: float = 0.0  # borrow fee per share


@dataclass
class StaticShortableProvider(ShortableProvider):
    """In-memory shortable provider with optional per-day limits and fees.

    ``table`` accepts either a direct ``ShortableLot`` per symbol or a mapping
    of ``date`` to ``ShortableLot`` for date-specific availability.
    """

    table: Dict[str, ShortableLot | Mapping[date, ShortableLot]]
    _borrowed: Dict[Tuple[str, date], int] = field(default_factory=dict)

    def _resolve_lot(self, symbol: str, on: date) -> Optional[ShortableLot]:
        entry = self.table.get(symbol)
        if entry is None:
            return None
        if isinstance(entry, Mapping):
            return entry.get(on)
        return entry

    def available_qty(self, symbol: str, on: Optional[date] = None) -> Optional[int]:
        on = on or date.today()
        lot = self._resolve_lot(symbol, on)
        if lot is None:
            return None
        borrowed = self._borrowed.get((symbol, on), 0)
        return max(lot.quantity - borrowed, 0)

    def borrow(self, symbol: str, quantity: int, on: Optional[date] = None) -> float:
        on = on or date.today()
        lot = self._resolve_lot(symbol, on)
        if lot is None:
            raise ValueError(f"Symbol {symbol} not shortable")
        borrowed = self._borrowed.get((symbol, on), 0)
        available = lot.quantity - borrowed
        if quantity > available:
            raise ValueError(
                f"Insufficient shortable quantity for {symbol}: requested {quantity}, available {available}"
            )
        self._borrowed[(symbol, on)] = borrowed + quantity
        return lot.fee * quantity

    def return_qty(self, symbol: str, quantity: int, on: Optional[date] = None) -> None:
        on = on or date.today()
        key = (symbol, on)
        borrowed = self._borrowed.get(key, 0)
        if quantity >= borrowed:
            self._borrowed.pop(key, None)
        else:
            self._borrowed[key] = borrowed - quantity

