"""Portfolio and position tracking utilities.

This module provides lightweight :class:`Portfolio` and :class:`Position`
classes along with convenience order helper functions for expressing
orders as notional values or portfolio weights.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class Position:
    """Represents a position in a single symbol."""

    symbol: str
    quantity: float
    avg_cost: float
    market_price: float

    @property
    def market_value(self) -> float:
        """Current market value of the position."""
        return self.quantity * self.market_price

    @property
    def unrealized_pnl(self) -> float:
        """Unrealized profit and loss for the position."""
        return (self.market_price - self.avg_cost) * self.quantity


@dataclass
class Portfolio:
    """Tracks cash and positions for a strategy."""

    cash: float = 0.0
    positions: Dict[str, Position] = field(default_factory=dict)

    def get_position(self, symbol: str) -> Optional[Position]:
        """Return the position for *symbol* if it exists."""
        return self.positions.get(symbol)

    @property
    def total_value(self) -> float:
        """Total portfolio value including cash.

        Positions are valued using their stored ``market_price``. Callers are
        responsible for keeping each position's ``market_price`` updated with
        the latest quotes before relying on this property.
        """
        return self.cash + sum(p.market_value for p in self.positions.values())

    def apply_fill(self, symbol: str, quantity: float, price: float, commission: float = 0.0) -> None:
        """Update portfolio based on an executed order.

        Parameters
        ----------
        symbol:
            Trading symbol of the fill.
        quantity:
            Signed quantity filled. Positive for buys, negative for sells.
        price:
            Fill price.
        commission:
            Optional commission paid for the trade.
        """
        cost = quantity * price
        self.cash -= cost + commission

        pos = self.positions.get(symbol)
        if pos is None:
            # opening new position
            self.positions[symbol] = Position(symbol, quantity, price, price)
            return

        new_qty = pos.quantity + quantity
        if new_qty == 0:
            # position closed
            del self.positions[symbol]
            return

        if quantity > 0:
            # increasing existing position
            total_cost = pos.avg_cost * pos.quantity + price * quantity
            pos.quantity = new_qty
            pos.avg_cost = total_cost / pos.quantity
        else:
            # reducing position; average cost unchanged
            pos.quantity = new_qty

        pos.market_price = price


def order_value(symbol: str, value: float, price: float) -> float:
    """Return quantity for an order targeting a notional ``value``."""
    if price == 0:
        raise ValueError("price must be non-zero")
    return value / price


def order_percent(portfolio: Portfolio, symbol: str, percent: float, price: float) -> float:
    """Return quantity sized at ``percent`` of the portfolio's total value."""
    target_value = portfolio.total_value * percent
    return order_value(symbol, target_value, price)


def order_target_percent(portfolio: Portfolio, symbol: str, percent: float, price: float) -> float:
    """Return quantity required to reach ``percent`` weight for ``symbol``."""
    current = portfolio.get_position(symbol)
    current_value = current.market_value if current else 0.0
    desired_value = portfolio.total_value * percent
    delta_value = desired_value - current_value
    return order_value(symbol, delta_value, price)


__all__ = [
    "Position",
    "Portfolio",
    "order_value",
    "order_percent",
    "order_target_percent",
]
