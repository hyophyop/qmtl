"""Symbol properties provider and order validation utilities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Dict


@dataclass(frozen=True)
class SymbolProperties:
    symbol: str
    tick_size: float = 0.01
    lot_size: int = 1
    min_qty: int = 1
    contract_multiplier: float = 1.0
    currency: str = "USD"
    price_precision: int = 2


class SymbolPropertiesProvider:
    """Provides symbol properties. Default implementation for US equities."""

    def __init__(self, table: Optional[Dict[str, SymbolProperties]] = None) -> None:
        self._table = table or {}

    def get(self, symbol: str) -> SymbolProperties:
        return self._table.get(symbol) or SymbolProperties(symbol)

    @staticmethod
    def round_price(price: float, tick_size: float) -> float:
        if tick_size <= 0:
            return price
        ticks = round(price / tick_size)
        return ticks * tick_size

    def validate_order(self, symbol: str, price: Optional[float], quantity: int) -> None:
        sp = self.get(symbol)
        if abs(quantity) < sp.min_qty:
            raise ValueError(f"Quantity {quantity} below min {sp.min_qty} for {symbol}")
        if abs(quantity) % sp.lot_size != 0:
            raise ValueError(f"Quantity {quantity} not multiple of lot size {sp.lot_size} for {symbol}")
        if price is not None:
            rounded = self.round_price(price, sp.tick_size)
            # Accept if already exactly on tick
            if abs(rounded - price) > 1e-9:
                raise ValueError(
                    f"Price {price} not aligned to tick {sp.tick_size} for {symbol} (expected {rounded})"
                )

