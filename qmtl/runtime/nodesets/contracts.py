from __future__ import annotations

from typing import Literal, TypedDict, NotRequired


class OrderIntent(TypedDict, total=False):
    symbol: str
    price: float
    side: NotRequired[Literal["BUY", "SELL"]]
    quantity: NotRequired[float]
    value: NotRequired[float]
    percent: NotRequired[float]
    target_percent: NotRequired[float]


class SizedOrder(OrderIntent):
    quantity: float


class ExecutionFillEvent(TypedDict, total=False):
    symbol: str
    quantity: float
    fill_price: float
    timestamp: int


class PortfolioSnapshot(TypedDict, total=False):
    cash: float
    positions: dict[str, dict]


__all__ = [
    "OrderIntent",
    "SizedOrder",
    "ExecutionFillEvent",
    "PortfolioSnapshot",
]

