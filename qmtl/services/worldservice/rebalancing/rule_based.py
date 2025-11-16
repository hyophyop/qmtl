from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping, Tuple

from .base import PositionSlice, RebalanceContext, RebalancePlan, Rebalancer, SymbolDelta


def _round_lot(symbol: str, qty: float, lot_size_by_symbol: Mapping[str, float] | None) -> float:
    if not lot_size_by_symbol:
        return qty
    lot = lot_size_by_symbol.get(symbol)
    if not lot or lot <= 0:
        return qty
    # Round toward zero to avoid overshooting targets
    return int(qty / lot) * lot


class ProportionalRebalancer(Rebalancer):
    """Rule-based proportional rebalancer.

    Behavior
    --------
    - World-level change: scale factor ``gw = world_after / world_before``.
    - Strategy-level change: ``gs[s] = (strategy_after[s] / strategy_before[s])``
      when both are positive; otherwise fall back to ``gw``.
    - Effective scale for a position belonging to strategy ``s`` is
      ``g = min(gw, gs[s])`` when downscaling; when upscaling use ``g = max(gw, gs[s])``.
      This keeps each strategy within its new cap while honoring the world cap.
    - Deltas are aggregated per (venue, symbol) and rounded to optional lot sizes.
    - Tiny notional changes below ``min_trade_notional`` are dropped to reduce fee churn.
    """

    def plan(self, ctx: RebalanceContext) -> RebalancePlan:
        gw = _compute_world_scale(ctx.world_alloc_before, ctx.world_alloc_after)
        gs = _compute_strategy_scales(ctx, gw)
        venue_symbol_delta_notional = _aggregate_position_deltas(ctx, gw, gs)
        deltas = _materialize_symbol_deltas(ctx, venue_symbol_delta_notional)

        return RebalancePlan(
            world_id=ctx.world_id,
            scale_world=gw,
            scale_by_strategy=gs,
            deltas=deltas,
        )


def _compute_world_scale(before: float, after: float) -> float:
    if before <= 0:
        return 1.0 if after > 0 else 0.0
    return after / before


def _compute_strategy_scales(ctx: RebalanceContext, gw: float) -> Dict[str, float]:
    gs: Dict[str, float] = {}
    for sid, after in ctx.strategy_alloc_after.items():
        before = ctx.strategy_alloc_before.get(sid, 0.0)
        if before <= 0.0:
            gs[sid] = gw if ctx.world_alloc_after > 0 else 0.0
        else:
            gs[sid] = after / before
    return gs


def _aggregate_position_deltas(
    ctx: RebalanceContext, gw: float, gs: Dict[str, float]
) -> Dict[tuple[str | None, str], float]:
    venue_symbol_delta_notional: Dict[tuple[str | None, str], float] = {}
    for pos in ctx.positions:
        s_factor = gs.get(pos.strategy_id, gw)
        target_notional = pos.notional * s_factor
        delta_notional = target_notional - pos.notional
        key = (pos.venue, pos.symbol)
        venue_symbol_delta_notional[key] = (
            venue_symbol_delta_notional.get(key, 0.0) + delta_notional
        )
    return venue_symbol_delta_notional


def _materialize_symbol_deltas(
    ctx: RebalanceContext,
    venue_symbol_delta_notional: Dict[tuple[str | None, str], float],
) -> List[SymbolDelta]:
    deltas: List[SymbolDelta] = []
    for (venue, symbol), d_notional in venue_symbol_delta_notional.items():
        if abs(d_notional) < ctx.min_trade_notional:
            continue
        marks: List[float] = [
            p.mark
            for p in ctx.positions
            if p.symbol == symbol and p.venue == venue and p.mark > 0
        ]
        if not marks:
            continue
        avg_mark = sum(marks) / len(marks)
        raw_qty = 0.0 if avg_mark == 0 else d_notional / avg_mark
        qty = _round_lot(symbol, raw_qty, ctx.lot_size_by_symbol)
        if qty == 0.0:
            continue
        deltas.append(SymbolDelta(symbol=symbol, delta_qty=qty, venue=venue))
    return deltas
