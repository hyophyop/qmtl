"""Shortable provider interface and default implementation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional, Dict


class ShortableProvider:
    """Provides short availability for symbols."""

    def is_shortable(self, symbol: str, on: Optional[date] = None) -> bool:
        return False

    def available_qty(self, symbol: str, on: Optional[date] = None) -> Optional[int]:
        return None


@dataclass
class StaticShortableProvider(ShortableProvider):
    table: Dict[str, bool]

    def is_shortable(self, symbol: str, on: Optional[date] = None) -> bool:
        return bool(self.table.get(symbol, False))

