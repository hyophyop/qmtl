from __future__ import annotations

"""Helpers to translate world rebalancing plans into order payloads.

These helpers do not submit orders. They convert per-world ``RebalancePlan``
or strategy-split deltas into order-shaped dictionaries that existing
publishing paths can consume.
"""

from dataclasses import dataclass
from typing import List, Mapping, Sequence, Tuple

import math

from qmtl.services.worldservice.rebalancing import (
    ExecutionDelta,
    RebalancePlan,
    SymbolDelta,
)


@dataclass(frozen=True)
class OrderOptions:
    time_in_force: str = "GTC"
    hedge_mode: bool | None = None
    reduce_only_for_negative: bool = True
    lot_size_by_symbol: Mapping[str, float] | None = None
    min_trade_notional: float | None = None
    marks_by_symbol: Mapping[Tuple[str | None, str], float] | None = None
    venue_policies: Mapping[str, "VenuePolicy"] | None = None


@dataclass(frozen=True)
class VenuePolicy:
    """Execution policy overrides for a trading venue."""

    supports_reduce_only: bool = True
    reduce_only_requires_ioc: bool = False
    default_time_in_force: str | None = None


def _round_to_lot(symbol: str, qty: float, *, options: OrderOptions) -> float:
    if not qty:
        return 0.0
    lots = options.lot_size_by_symbol or {}
    lot = lots.get(symbol)
    if not lot or lot <= 0:
        return qty
    signed = math.copysign(1.0, qty)
    abs_qty = abs(qty)
    steps = math.floor(abs_qty / lot)
    rounded = steps * lot
    return signed * rounded


def _meets_notional_threshold(
    symbol: str,
    venue: str | None,
    qty: float,
    *,
    options: OrderOptions,
) -> bool:
    if qty <= 0:
        return True
    min_notional = options.min_trade_notional
    if not min_notional or min_notional <= 0:
        return True
    marks = options.marks_by_symbol or {}
    mark = marks.get((venue, symbol)) or marks.get((None, symbol))
    if not mark or mark <= 0:
        return True
    return abs(qty) * mark >= min_notional


def _resolve_time_in_force(
    tif: str,
    *,
    reduce_only: bool,
    venue: str | None,
    options: OrderOptions,
) -> str:
    policies = options.venue_policies or {}
    policy = policies.get(venue or "")
    if policy is None and venue:
        policy = policies.get(venue.lower())
    if policy is None:
        policy = policies.get("*")
    if policy is None:
        return tif
    if reduce_only and not policy.supports_reduce_only:
        return tif
    if reduce_only and policy.reduce_only_requires_ioc:
        return "IOC"
    if policy.default_time_in_force:
        return policy.default_time_in_force
    return tif


def _apply_reduce_only_flag(
    *,
    reduce_only: bool,
    venue: str | None,
    options: OrderOptions,
) -> bool:
    if not reduce_only:
        return False
    policies = options.venue_policies or {}
    policy = policies.get(venue or "") or policies.get((venue or "").lower())
    if policy is None:
        policy = policies.get("*")
    if policy is None:
        return reduce_only
    return policy.supports_reduce_only


def _build_order(
    symbol: str,
    qty: float,
    *,
    reduce_only: bool,
    tif: str,
    venue: str | None,
    options: OrderOptions,
) -> dict | None:
    qty_rounded = _round_to_lot(symbol, qty, options=options)
    if qty_rounded == 0:
        return None
    if not _meets_notional_threshold(symbol, venue, qty_rounded, options=options):
        return None
    effective_reduce_only = _apply_reduce_only_flag(
        reduce_only=reduce_only, venue=venue, options=options
    )
    effective_tif = _resolve_time_in_force(
        tif,
        reduce_only=effective_reduce_only,
        venue=venue,
        options=options,
    )
    side = "buy" if qty_rounded >= 0 else "sell"
    payload = {
        "symbol": symbol,
        "quantity": qty_rounded,
        "side": side,
        "time_in_force": effective_tif,
    }
    if venue is not None:
        payload["venue"] = venue
    if effective_reduce_only:
        payload["reduce_only"] = True
    if options.hedge_mode is not None:
        payload["hedge_mode"] = options.hedge_mode
    return payload


def orders_from_world_plan(plan: RebalancePlan, *, options: OrderOptions | None = None) -> List[dict]:
    """Convert a per-world ``RebalancePlan`` into order payloads.

    Negative deltas become reduce-only orders (when ``reduce_only_for_negative`` is
    True) to enforce non-increasing exposure on cuts.
    """
    opts = options or OrderOptions()
    orders: List[dict] = []
    for d in plan.deltas:
        reduce_only = bool(opts.reduce_only_for_negative and d.delta_qty < 0)
        order = _build_order(
            d.symbol,
            d.delta_qty,
            reduce_only=reduce_only,
            tif=opts.time_in_force,
            venue=d.venue,
            options=opts,
        )
        if order is not None:
            orders.append(order)
    return orders


def orders_from_strategy_deltas(
    deltas: Sequence[ExecutionDelta], *, options: OrderOptions | None = None
) -> List[dict]:
    """Convert per-strategy deltas into order payloads.

    Caller should route orders to the appropriate strategy pipelines. This
    helper only generates the payloads.
    """
    opts = options or OrderOptions()
    orders: List[dict] = []
    for d in deltas:
        reduce_only = bool(opts.reduce_only_for_negative and d.delta_qty < 0)
        order = _build_order(
            d.symbol,
            d.delta_qty,
            reduce_only=reduce_only,
            tif=opts.time_in_force,
            venue=d.venue,
            options=opts,
        )
        if order is not None:
            orders.append(order)
    return orders


def orders_from_symbol_deltas(
    deltas: Sequence[SymbolDelta], *, options: OrderOptions | None = None
) -> List[dict]:
    """Convert aggregated symbol deltas (global view) into order payloads."""
    opts = options or OrderOptions()
    orders: List[dict] = []
    for d in deltas:
        reduce_only = bool(opts.reduce_only_for_negative and d.delta_qty < 0)
        order = _build_order(
            d.symbol,
            d.delta_qty,
            reduce_only=reduce_only,
            tif=opts.time_in_force,
            venue=d.venue,
            options=opts,
        )
        if order is not None:
            orders.append(order)
    return orders


__all__ = [
    "OrderOptions",
    "VenuePolicy",
    "orders_from_world_plan",
    "orders_from_strategy_deltas",
    "orders_from_symbol_deltas",
]
