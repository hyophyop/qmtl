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
        if ctx.world_alloc_before <= 0:
            # No prior allocation → only strategy deltas matter; treat world scale as 1.0
            gw = 1.0 if ctx.world_alloc_after > 0 else 0.0
        else:
            gw = ctx.world_alloc_after / ctx.world_alloc_before

        # Precompute strategy scaling
        gs: Dict[str, float] = {}
        for sid, after in ctx.strategy_alloc_after.items():
            before = ctx.strategy_alloc_before.get(sid, 0.0)
            if before <= 0.0:
                # New strategy allocation; let world scaling drive
                gs[sid] = gw if ctx.world_alloc_after > 0 else 0.0
            else:
                gs[sid] = after / before

        # Aggregate current exposure per (venue, symbol) and per-strategy
        # and compute per-position target → delta.
        venue_symbol_delta_notional: Dict[tuple[str | None, str], float] = {}

        for pos in ctx.positions:
            # Scaling semantics: preserve each strategy sleeve's relative structure
            # and apply a single scalar to its entire vector. When explicit
            # strategy totals are provided, use the ratio (after/before).
            # Otherwise, cascade the world factor.
            s_factor = gs.get(pos.strategy_id, gw)
            target_notional = pos.notional * s_factor
            delta_notional = target_notional - pos.notional
            key = (pos.venue, pos.symbol)
            venue_symbol_delta_notional[key] = venue_symbol_delta_notional.get(key, 0.0) + delta_notional

        # Convert notional to quantity deltas with lot rounding and thresholding
        deltas: List[SymbolDelta] = []
        for (venue, symbol), d_notional in venue_symbol_delta_notional.items():
            if abs(d_notional) < ctx.min_trade_notional:
                continue
            # We need a representative mark to convert to quantity. Use
            # the average mark across slices for this (venue, symbol).
            marks: List[float] = [
                p.mark for p in ctx.positions if p.symbol == symbol and p.venue == venue and p.mark > 0
            ]
            if not marks:
                # Cannot size without a mark; skip safely
                continue
            avg_mark = sum(marks) / len(marks)
            raw_qty = 0.0 if avg_mark == 0 else d_notional / avg_mark
            qty = _round_lot(symbol, raw_qty, ctx.lot_size_by_symbol)
            if qty == 0.0:
                continue
            deltas.append(SymbolDelta(symbol=symbol, delta_qty=qty, venue=venue))

        return RebalancePlan(
            world_id=ctx.world_id,
            scale_world=gw,
            scale_by_strategy=gs,
            deltas=deltas,
        )
