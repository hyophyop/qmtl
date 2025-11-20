from __future__ import annotations

"""Helpers to translate world rebalancing plans into order payloads.

These helpers do not submit orders. They convert per-world ``RebalancePlan``
or strategy-split deltas into order-shaped dictionaries that existing
publishing paths can consume.
"""

from dataclasses import dataclass
from typing import List, Mapping, Sequence, Tuple

import math

from qmtl.services.gateway.instrument_constraints import (
    ConstraintViolation,
    ConstraintViolationError,
    InstrumentConstraint,
    InstrumentConstraints,
    ResolvedInstrument,
)

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
    instrument_constraints: InstrumentConstraints | None = None
    constraint_violation_sink: List[ConstraintViolation] | None = None
    raise_on_violation: bool = False


@dataclass(frozen=True)
class VenuePolicy:
    """Execution policy overrides for a trading venue."""

    supports_reduce_only: bool = True
    reduce_only_requires_ioc: bool = False
    default_time_in_force: str | None = None


def _handle_violation(violation: ConstraintViolation, *, options: OrderOptions) -> None:
    sink = options.constraint_violation_sink
    if sink is not None:
        sink.append(violation)
    if options.raise_on_violation:
        raise ConstraintViolationError(violation)


def _resolve_instrument(symbol: str, venue: str | None, *, options: OrderOptions) -> ResolvedInstrument:
    constraints = options.instrument_constraints
    resolved = (
        constraints.resolve(venue, symbol)
        if constraints is not None
        else ResolvedInstrument(
            venue=venue,
            input_symbol=symbol,
            symbol=symbol,
            constraint=InstrumentConstraint(),
        )
    )

    lot_override = None
    if options.lot_size_by_symbol:
        lots = options.lot_size_by_symbol
        lot_override = lots.get(resolved.symbol) or lots.get(symbol)

    min_notional = resolved.constraint.min_notional
    if options.min_trade_notional and options.min_trade_notional > 0:
        if min_notional is None or min_notional < options.min_trade_notional:
            min_notional = options.min_trade_notional

    constraint = InstrumentConstraint(
        lot_size=lot_override if lot_override is not None else resolved.constraint.lot_size,
        min_notional=min_notional,
        tick_size=resolved.constraint.tick_size,
    )

    return ResolvedInstrument(
        venue=resolved.venue,
        input_symbol=resolved.input_symbol,
        symbol=resolved.symbol,
        constraint=constraint,
    )


def _lookup_mark(
    resolved: ResolvedInstrument, *, options: OrderOptions
) -> tuple[float | None, object | None]:
    marks = options.marks_by_symbol or {}
    symbol = resolved.symbol
    original = resolved.input_symbol
    venue = resolved.venue
    candidates: list[object] = []
    if venue is not None:
        candidates.append((venue, symbol))
        candidates.append((venue, original))
        venue_lower = venue.lower()
        if venue_lower != venue:
            candidates.append((venue_lower, symbol))
            candidates.append((venue_lower, original))
    candidates.append((None, symbol))
    candidates.append((None, original))
    candidates.append(symbol)
    if original != symbol:
        candidates.append(original)
    getter = getattr(marks, "get", None)
    for key in candidates:
        if getter is not None:
            value = getter(key, None)
        else:  # pragma: no cover - fallback for exotic mappings without ``get``
            try:
                value = marks[key]  # type: ignore[index]
            except (KeyError, TypeError):
                continue
        if value is not None:
            return value, key
    return None, None


def _round_to_lot(qty: float, lot_size: float | None) -> tuple[float, int]:
    if not qty:
        return 0.0, 0
    if lot_size is None or lot_size <= 0:
        return qty, 0
    abs_qty = abs(qty)
    steps = math.floor(abs_qty / lot_size + 1e-12)
    rounded = math.copysign(steps * lot_size, qty)
    return rounded, steps


def _evaluate_notional(
    qty: float,
    resolved: ResolvedInstrument,
    mark: float | None,
    mark_source: object | None,
) -> tuple[bool, ConstraintViolation | None]:
    min_notional = resolved.constraint.min_notional
    if qty == 0:
        return True, None
    if min_notional is None or min_notional <= 0:
        return True, None
    if mark is None or mark <= 0:
        return (
            False,
            ConstraintViolation(
                venue=resolved.venue,
                symbol=resolved.symbol,
                reason="missing-mark",
                details={
                    "min_notional": min_notional,
                    "mark_source": mark_source,
                },
            ),
        )
    notional = abs(qty) * mark
    if notional + 1e-12 < min_notional:
        return (
            False,
            ConstraintViolation(
                venue=resolved.venue,
                symbol=resolved.symbol,
                reason="min-notional",
                details={
                    "min_notional": min_notional,
                    "mark": mark,
                    "quantity": qty,
                },
            ),
        )
    return True, None


def _apply_constraints(
    symbol: str,
    qty: float,
    venue: str | None,
    *,
    options: OrderOptions,
) -> tuple[float | None, ResolvedInstrument]:
    resolved = _resolve_instrument(symbol, venue, options=options)
    rounded_qty, steps = _round_to_lot(qty, resolved.constraint.lot_size)
    if qty and resolved.constraint.lot_size and resolved.constraint.lot_size > 0 and steps == 0:
        violation = ConstraintViolation(
            venue=resolved.venue,
            symbol=resolved.symbol,
            reason="lot-size",
            details={
                "requested_qty": qty,
                "lot_size": resolved.constraint.lot_size,
            },
        )
        _handle_violation(violation, options=options)
        return None, resolved

    mark, mark_source = _lookup_mark(resolved, options=options)
    meets_notional, notional_violation = _evaluate_notional(rounded_qty, resolved, mark, mark_source)
    if not meets_notional:
        if notional_violation is None:
            raise ValueError("notional constraint violation details missing")
        _handle_violation(notional_violation, options=options)
        return None, resolved

    return rounded_qty, resolved


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
    qty_adjusted, resolved = _apply_constraints(symbol, qty, venue, options=options)
    if qty_adjusted is None or qty_adjusted == 0:
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
    side = "buy" if qty_adjusted >= 0 else "sell"
    payload = {
        "symbol": resolved.symbol,
        "quantity": qty_adjusted,
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
