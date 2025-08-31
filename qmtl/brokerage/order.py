"""Order and fill data structures for brokerage models."""

# Source: docs/architecture/lean_brokerage_model.md

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class OrderType(str, Enum):
    """Supported order types."""

    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class TimeInForce(str, Enum):
    """Time-in-Force policies."""

    DAY = "day"
    GTC = "gtc"
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
    """

    symbol: str
    quantity: int
    price: float
    type: OrderType = OrderType.MARKET
    tif: TimeInForce = TimeInForce.DAY
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None


@dataclass
class Fill:
    """Executed order details."""

    symbol: str
    quantity: int
    price: float
    fee: float = 0.0


@dataclass
class Account:
    """Account holding cash for trading (simplified)."""

    cash: float
