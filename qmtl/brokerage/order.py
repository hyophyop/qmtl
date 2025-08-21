"""Order and fill data structures for brokerage models."""

# Source: docs/architecture/lean_brokerage_model.md

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Order:
    """Simple order representation.

    Attributes:
        symbol: Trading pair or ticker.
        quantity: Number of units to buy (>0) or sell (<0).
        price: Expected execution price used for buying power checks.
    """

    symbol: str
    quantity: int
    price: float


@dataclass
class Fill:
    """Executed order details."""

    symbol: str
    quantity: int
    price: float
    fee: float = 0.0


@dataclass
class Account:
    """Account holding cash for trading."""

    cash: float
