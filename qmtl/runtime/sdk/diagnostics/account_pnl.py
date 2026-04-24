"""Account-level PnL summaries for local strategy iteration.

This module is intentionally independent from Runner, Gateway, WorldService,
and the risk hub. It provides an opt-in helper for fast local validation loops
that already have fill-like records and optional mark prices.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping


@dataclass(frozen=True, slots=True)
class AccountFill:
    """A normalized local fill.

    ``quantity`` is signed: positive quantities buy/increase long exposure and
    negative quantities sell/increase short exposure.
    """

    symbol: str
    quantity: float
    price: float
    commission: float = 0.0


@dataclass(frozen=True, slots=True)
class AccountPnlPosition:
    """Open position included in an account-level PnL summary."""

    symbol: str
    quantity: float
    avg_cost: float
    mark_price: float

    @property
    def market_value(self) -> float:
        """Signed mark-to-market value for the position."""

        return self.quantity * self.mark_price

    @property
    def unrealized_pnl(self) -> float:
        """Price PnL for the open position, before future exit fees."""

        return (self.mark_price - self.avg_cost) * self.quantity


@dataclass(frozen=True, slots=True)
class AccountPnlSummary:
    """Account-level PnL summary for local validation loops."""

    starting_cash: float
    ending_cash: float
    equity: float
    realized_pnl: float
    unrealized_pnl: float
    fees: float
    total_pnl: float
    positions: Mapping[str, AccountPnlPosition]


@dataclass(slots=True)
class _OpenPosition:
    quantity: float
    avg_cost: float
    last_price: float


def summarize_account_pnl(
    fills: Iterable[AccountFill | Mapping[str, Any] | Any],
    *,
    marks: Mapping[str, float] | None = None,
    starting_cash: float = 0.0,
) -> AccountPnlSummary:
    """Summarize account-level PnL from local fills and optional marks.

    Accepted fill shapes:
    - :class:`AccountFill`, with signed ``quantity``.
    - Mapping/object with ``symbol``, ``quantity``, and ``price``.
    - Mapping/object with execution-model style ``side``, ``quantity``, and
      ``fill_price``.

    ``realized_pnl`` and ``unrealized_pnl`` are price PnL before fees. ``fees``
    captures paid commissions, and ``total_pnl`` is net of fees.
    """

    marks = marks or {}
    cash = float(starting_cash)
    realized_pnl = 0.0
    fees = 0.0
    positions: dict[str, _OpenPosition] = {}

    for raw_fill in fills:
        fill = _normalize_fill(raw_fill)
        cash -= fill.quantity * fill.price + fill.commission
        fees += fill.commission
        realized_pnl += _apply_position_fill(positions, fill)

    open_positions = _mark_positions(positions, marks)
    unrealized_pnl = sum(position.unrealized_pnl for position in open_positions.values())
    equity = cash + sum(position.market_value for position in open_positions.values())
    total_pnl = equity - float(starting_cash)

    return AccountPnlSummary(
        starting_cash=float(starting_cash),
        ending_cash=cash,
        equity=equity,
        realized_pnl=realized_pnl,
        unrealized_pnl=unrealized_pnl,
        fees=fees,
        total_pnl=total_pnl,
        positions=open_positions,
    )


def _apply_position_fill(positions: dict[str, _OpenPosition], fill: AccountFill) -> float:
    current = positions.get(fill.symbol)
    if current is None:
        positions[fill.symbol] = _OpenPosition(
            quantity=fill.quantity,
            avg_cost=fill.price,
            last_price=fill.price,
        )
        return 0.0

    current.last_price = fill.price
    same_direction = current.quantity * fill.quantity > 0
    if same_direction:
        total_quantity = current.quantity + fill.quantity
        total_cost = current.avg_cost * abs(current.quantity) + fill.price * abs(fill.quantity)
        current.quantity = total_quantity
        current.avg_cost = total_cost / abs(total_quantity)
        return 0.0

    closed_quantity = min(abs(current.quantity), abs(fill.quantity))
    realized_pnl = closed_quantity * (fill.price - current.avg_cost) * _sign(current.quantity)
    new_quantity = current.quantity + fill.quantity

    if new_quantity == 0:
        del positions[fill.symbol]
    elif current.quantity * new_quantity < 0:
        current.quantity = new_quantity
        current.avg_cost = fill.price
    else:
        current.quantity = new_quantity

    return realized_pnl


def _mark_positions(
    positions: Mapping[str, _OpenPosition],
    marks: Mapping[str, float],
) -> dict[str, AccountPnlPosition]:
    marked: dict[str, AccountPnlPosition] = {}
    for symbol, position in positions.items():
        mark_price = _positive_float(marks.get(symbol, position.last_price), f"marks[{symbol!r}]")
        marked[symbol] = AccountPnlPosition(
            symbol=symbol,
            quantity=position.quantity,
            avg_cost=position.avg_cost,
            mark_price=mark_price,
        )
    return marked


def _normalize_fill(raw_fill: AccountFill | Mapping[str, Any] | Any) -> AccountFill:
    if isinstance(raw_fill, AccountFill):
        fill = raw_fill
    else:
        symbol = str(_read_field(raw_fill, "symbol"))
        quantity = _non_zero_float(_read_field(raw_fill, "quantity"), "quantity")
        price = _positive_float(_read_price(raw_fill), "price")
        side = _read_optional_field(raw_fill, "side")
        signed_quantity = _signed_quantity(quantity, side)
        commission = _non_negative_float(
            _read_optional_field(raw_fill, "commission", "fee", default=0.0),
            "commission",
        )
        fill = AccountFill(symbol=symbol, quantity=signed_quantity, price=price, commission=commission)

    if not fill.symbol:
        raise ValueError("symbol must be non-empty")
    if fill.quantity == 0:
        raise ValueError("quantity must be non-zero")
    _positive_float(fill.price, "price")
    _non_negative_float(fill.commission, "commission")
    return fill


def _read_price(raw_fill: Mapping[str, Any] | Any) -> Any:
    return _read_optional_field(raw_fill, "price", "fill_price", default=_MISSING)


def _read_field(raw: Mapping[str, Any] | Any, name: str) -> Any:
    value = _read_optional_field(raw, name, default=_MISSING)
    if value is _MISSING:
        raise ValueError(f"{name} is required")
    return value


def _read_optional_field(
    raw: Mapping[str, Any] | Any,
    *names: str,
    default: Any = None,
) -> Any:
    if isinstance(raw, Mapping):
        for name in names:
            if name in raw:
                return raw[name]
        return default

    for name in names:
        if hasattr(raw, name):
            return getattr(raw, name)
    return default


def _signed_quantity(quantity: float, side: Any) -> float:
    if side is None:
        return quantity

    side_value = getattr(side, "value", side)
    side_name = str(side_value).lower()
    if side_name == "buy":
        return abs(quantity)
    if side_name == "sell":
        return -abs(quantity)
    raise ValueError("side must be 'buy' or 'sell'")


def _positive_float(value: Any, name: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a positive number") from exc
    if parsed <= 0:
        raise ValueError(f"{name} must be a positive number")
    return parsed


def _non_negative_float(value: Any, name: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be non-negative") from exc
    if parsed < 0:
        raise ValueError(f"{name} must be non-negative")
    return parsed


def _non_zero_float(value: Any, name: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be non-zero") from exc
    if parsed == 0:
        raise ValueError(f"{name} must be non-zero")
    return parsed


def _sign(value: float) -> int:
    return 1 if value > 0 else -1


class _Missing:
    pass


_MISSING = _Missing()


__all__ = [
    "AccountFill",
    "AccountPnlPosition",
    "AccountPnlSummary",
    "summarize_account_pnl",
]
