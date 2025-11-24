"""Core data structures for the execution modeling package."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

__all__ = [
    "OrderType",
    "OrderSide",
    "TimeInForce",
    "OrderStatus",
    "ExecutionFill",
    "MarketData",
    "OpenOrder",
]


class OrderType(str, Enum):
    """Supported order types."""

    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class OrderSide(str, Enum):
    """Order directions."""

    BUY = "buy"
    SELL = "sell"


class TimeInForce(str, Enum):
    """Time-in-force policies."""

    GTC = "gtc"
    IOC = "ioc"
    FOK = "fok"


class OrderStatus(str, Enum):
    """Lifecycle states for an order."""

    NEW = "new"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELED = "canceled"
    EXPIRED = "expired"


@dataclass(slots=True)
class ExecutionFill:
    """Represents a completed (possibly partial) fill."""

    order_id: str
    symbol: str
    side: OrderSide
    quantity: float
    requested_price: float
    fill_price: float
    fill_time: int
    commission: float
    slippage: float
    market_impact: float

    @property
    def total_cost(self) -> float:
        """Total execution cost including commission and slippage."""

        return self.commission + abs(self.slippage * self.quantity)

    @property
    def execution_shortfall(self) -> float:
        """Absolute price difference between the request and actual fill."""

        return abs(self.fill_price - self.requested_price)


@dataclass(slots=True)
class MarketData:
    """Minimal market data required for execution modeling."""

    timestamp: int
    bid: float
    ask: float
    last: float
    volume: float

    @property
    def spread(self) -> float:
        """Bid-ask spread."""

        return self.ask - self.bid

    @property
    def mid_price(self) -> float:
        """Mid-market price."""

        return (self.bid + self.ask) / 2.0

    @property
    def spread_pct(self) -> float:
        """Spread expressed as a percentage of the mid price."""

        mid = self.mid_price
        return (self.spread / mid) if mid > 0 else 0.0


@dataclass(slots=True)
class OpenOrder:
    """Represents an order that may persist across bars."""

    order_id: str
    symbol: str
    side: OrderSide
    quantity: float
    order_type: OrderType
    requested_price: float
    tif: TimeInForce = TimeInForce.GTC
    status: OrderStatus = OrderStatus.NEW
    remaining: float = 0.0
    fills: list[ExecutionFill] = field(default_factory=list)
    submitted_time: int = 0

    def __post_init__(self) -> None:
        if self.remaining <= 0:
            self.remaining = self.quantity
