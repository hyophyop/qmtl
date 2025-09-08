"""Order and fill data structures for brokerage models."""

# Source: docs/architecture/lean_brokerage_model.md

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional
from datetime import datetime

from .cashbook import Cashbook


class OrderType(str, Enum):
    """Supported order types."""

    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"
    MOO = "market_on_open"
    MOC = "market_on_close"
    TRAILING_STOP = "trailing_stop"


class TimeInForce(str, Enum):
    """Time-in-Force policies."""

    DAY = "day"
    GTC = "gtc"
    GTD = "gtd"
    IOC = "ioc"
    FOK = "fok"


@dataclass
class Order:
    """Order representation.

    Attributes:
        symbol: Trading pair or ticker.
        quantity: Number of units to buy (>0) or sell (<0).
        price: Expected price reference used for buying power checks.
        type: Order type.
        tif: Time-in-Force policy.
        limit_price: Limit price for limit/stop-limit orders.
        stop_price: Stop trigger for stop/stop-limit orders.
        expire_at: Expiration timestamp for GTD orders.
        trail_amount: Trailing offset for trailing stop orders.
    """

    symbol: str
    quantity: int
    price: float
    type: OrderType = OrderType.MARKET
    tif: TimeInForce = TimeInForce.DAY
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    expire_at: Optional[datetime] = None
    trail_amount: Optional[float] = None


@dataclass
class Fill:
    """Executed order details."""

    symbol: str
    quantity: int
    price: float
    fee: float = 0.0


class Account:
    """Account holding cash across multiple currencies via a cashbook."""

    def __init__(self, cash: float = 0.0, base_currency: str = "USD") -> None:
        self.base_currency = base_currency
        self.cashbook = Cashbook()
        self.cashbook.set(base_currency, cash)

    @property
    def cash(self) -> float:  # backwards compatibility for single-currency tests
        return self.cashbook.get(self.base_currency).balance

    @cash.setter
    def cash(self, value: float) -> None:
        self.cashbook.set(self.base_currency, value)
