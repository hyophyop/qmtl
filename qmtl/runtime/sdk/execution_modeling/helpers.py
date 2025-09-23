"""Pure helper functions supporting the execution modeling engine."""

from __future__ import annotations

from .models import MarketData, OrderSide, OrderType

__all__ = [
    "calculate_commission",
    "base_slippage_from_bps",
    "calculate_market_impact",
    "spread_cost",
    "calculate_slippage",
    "determine_fill_quantity",
    "apply_latency",
]


def calculate_commission(trade_value: float, rate: float, minimum: float) -> float:
    """Return the commission owed for a trade value."""

    commission = trade_value * rate
    return max(commission, minimum)


def base_slippage_from_bps(mid_price: float, base_slippage_bps: float) -> float:
    """Convert basis points of slippage to absolute price terms."""

    if mid_price <= 0:
        return 0.0
    return mid_price * (base_slippage_bps / 10_000.0)


def calculate_market_impact(
    quantity: float, market_data: MarketData, coeff: float
) -> float:
    """Estimate market impact based on order size and available volume."""

    if market_data.volume <= 0 or quantity <= 0:
        return 0.0
    volume_ratio = quantity / market_data.volume
    return coeff * volume_ratio * market_data.mid_price


def spread_cost(order_type: OrderType, market_data: MarketData) -> float:
    """Compute the half-spread cost applied to market orders."""

    if order_type != OrderType.MARKET:
        return 0.0
    return market_data.spread / 2.0


def calculate_slippage(
    market_data: MarketData,
    order_type: OrderType,
    side: OrderSide,
    quantity: float,
    *,
    base_slippage_bps: float,
    market_impact_coeff: float,
) -> float:
    """Aggregate directional slippage in price terms."""

    base_slippage = base_slippage_from_bps(market_data.mid_price, base_slippage_bps)
    impact = calculate_market_impact(quantity, market_data, market_impact_coeff)
    spread = spread_cost(order_type, market_data)
    total_slippage = base_slippage + impact + spread
    return total_slippage if side == OrderSide.BUY else -total_slippage


def determine_fill_quantity(
    remaining: float,
    *,
    allow_partial: bool,
    max_partial_fill: float | None,
) -> float | None:
    """Return the quantity to fill for the current attempt."""

    if remaining <= 0:
        return 0.0

    if not allow_partial:
        if max_partial_fill is not None and max_partial_fill < remaining:
            return None
        return remaining

    if max_partial_fill is None:
        return remaining

    return min(remaining, max_partial_fill)


def apply_latency(timestamp: int, latency_ms: int) -> int:
    """Adjust a timestamp by simulated latency."""

    if latency_ms < 0:
        raise ValueError("latency_ms must be non-negative")
    return timestamp + latency_ms
