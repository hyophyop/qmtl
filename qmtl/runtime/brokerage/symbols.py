"""Symbol properties provider and order validation utilities."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import csv
from typing import Optional, Dict, Any


@dataclass(frozen=True)
class SymbolProperties:
    symbol: str
    asset_class: str = "equity"
    tick_size: float = 0.01
    lot_size: int = 1
    min_qty: int = 1
    contract_multiplier: float = 1.0
    currency: str = "USD"
    price_precision: int = 2


ASSET_DEFAULTS: Dict[str, Dict[str, Any]] = {
    "equity": {
        "asset_class": "equity",
        "tick_size": 0.01,
        "lot_size": 1,
        "min_qty": 1,
        "contract_multiplier": 1.0,
        "currency": "USD",
        "price_precision": 2,
    },
    "futures": {
        "asset_class": "futures",
        "tick_size": 0.25,
        "lot_size": 1,
        "min_qty": 1,
        "contract_multiplier": 1.0,
        "currency": "USD",
        "price_precision": 2,
    },
    "option": {
        "asset_class": "option",
        "tick_size": 0.01,
        "lot_size": 100,
        "min_qty": 100,
        "contract_multiplier": 100.0,
        "currency": "USD",
        "price_precision": 2,
    },
}


def _infer_precision(tick: float) -> int:
    if tick <= 0:
        return 2
    s = f"{tick:.10f}".rstrip("0")
    if "." in s:
        return len(s.split(".")[1])
    return 0


class SymbolPropertiesProvider:
    """Provides symbol properties. Loads from JSON/CSV with asset-class defaults."""

    def __init__(
        self,
        table: Optional[Dict[str, SymbolProperties]] = None,
        file: Optional[str | Path] = None,
    ) -> None:
        if table is not None:
            self._table = self._normalize_table(table)
        else:
            path = Path(file) if file is not None else Path(__file__).with_name("symbol_properties.json")
            self._table = self._load_file(path) if path.exists() else {}

    def _normalize_table(self, table: Dict[str, Any]) -> Dict[str, SymbolProperties]:
        out: Dict[str, SymbolProperties] = {}
        for sym, props in table.items():
            if isinstance(props, SymbolProperties):
                out[sym] = props
            else:
                row = {"symbol": sym, **props}
                out[sym] = self._make_properties(row)
        return out

    def _load_file(self, path: Path) -> Dict[str, SymbolProperties]:
        rows: list[Dict[str, Any]]
        if path.suffix.lower() == ".json":
            with path.open() as f:
                data = json.load(f)
            if isinstance(data, dict):
                rows = list(data.values())
            else:
                rows = data
        elif path.suffix.lower() == ".csv":
            with path.open(newline="") as f:
                rows = list(csv.DictReader(f))
        else:
            raise ValueError("Unsupported symbol properties file format")
        table: Dict[str, SymbolProperties] = {}
        for row in rows:
            sp = self._make_properties(row)
            table[sp.symbol] = sp
        return table

    def _make_properties(self, row: Dict[str, Any]) -> SymbolProperties:
        asset = row.get("asset_class", "equity")
        defaults = ASSET_DEFAULTS.get(asset, ASSET_DEFAULTS["equity"]).copy()
        defaults.update(row)
        if "price_precision" not in defaults:
            defaults["price_precision"] = _infer_precision(defaults["tick_size"])
        return SymbolProperties(**defaults)

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

