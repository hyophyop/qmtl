from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Mapping, Optional, Tuple

from .base import (
    PositionSlice,
    RebalancePlan,
    Rebalancer,
    RebalanceContext,
    SymbolDelta,
)
from .rule_based import ProportionalRebalancer


@dataclass
class MultiWorldRebalanceContext:
    """Inputs for a multi-world coordinated rebalance.

    Notes
    -----
    - Strategy weights are not manually tuned here. By default, strategy
      exposures cascade from world-level scaling ("scale-only"). If a separate
      performance module has already computed new strategy weights, provide
      them via ``strategy_alloc_after_total`` to let scaling reflect those
      changes as the second trigger.
    - Cross-world netting is computed for analysis; callers can choose to
      enforce per-world orders only or enable shared-account netting policies.
    """

    total_equity: float
    # World allocation ratios relative to total_equity (0.0–1.0)
    world_alloc_before: Mapping[str, float]
    world_alloc_after: Mapping[str, float]
    # Optional per-strategy allocations relative to total_equity.
    # If omitted, strategy scaling falls back to world cascade (scale-only).
    strategy_alloc_before_total: Mapping[str, Mapping[str, float]] | None = None
    strategy_alloc_after_total: Mapping[str, Mapping[str, float]] | None = None
    # Positions across all worlds (world_id required)
    positions: List[PositionSlice] = None
    # Execution considerations
    min_trade_notional: float = 0.0
    lot_size_by_symbol: Mapping[str, float] | None = None


@dataclass
class MultiWorldRebalancePlan:
    per_world: Dict[str, RebalancePlan]
    global_deltas: List[SymbolDelta]


class MultiWorldProportionalRebalancer:
    """Coordinate proportional rebalancing across multiple worlds.

    - Applies the proportional rule per world (same as ``ProportionalRebalancer``)
      with cascade into strategies.
    - Produces a per-world plan and a global aggregated delta view (net across worlds).
    """

    def __init__(self) -> None:
        self._single = ProportionalRebalancer()

    def plan(self, ctx: MultiWorldRebalanceContext) -> MultiWorldRebalancePlan:
        per_world_positions = self._group_positions(ctx.positions)
        per_world_plans = self._build_per_world_plans(ctx, per_world_positions)
        global_deltas = self._build_global_deltas(ctx, per_world_positions, per_world_plans)
        return MultiWorldRebalancePlan(per_world=per_world_plans, global_deltas=global_deltas)

    def _group_positions(
        self, positions: Optional[List[PositionSlice]]
    ) -> Dict[str, List[PositionSlice]]:
        grouped: Dict[str, List[PositionSlice]] = {}
        for pos in positions or []:
            grouped.setdefault(pos.world_id, []).append(pos)
        return grouped

    def _derive_strategy_targets(
        self,
        ctx: MultiWorldRebalanceContext,
        wid: str,
        positions: List[PositionSlice],
    ) -> Tuple[Mapping[str, float], Mapping[str, float]]:
        s_before_total = (ctx.strategy_alloc_before_total or {}).get(wid)
        s_after_total = (ctx.strategy_alloc_after_total or {}).get(wid)

        if s_before_total is None:
            totals: Dict[str, float] = {}
            world_total = 0.0
            for pos in positions:
                notional = pos.qty * pos.mark
                totals[pos.strategy_id] = totals.get(pos.strategy_id, 0.0) + notional
                world_total += notional
            if world_total > 0:
                denom = ctx.total_equity if ctx.total_equity > 0 else world_total
                s_before_total = {sid: value / denom for sid, value in totals.items()}
            else:
                s_before_total = {sid: 0.0 for sid in totals.keys()}

        if s_after_total is None:
            gw_before = ctx.world_alloc_before.get(wid, 0.0)
            gw_after = ctx.world_alloc_after.get(wid, 0.0)
            factor = (gw_after / gw_before) if gw_before > 0 else (1.0 if gw_after > 0 else 0.0)
            s_after_total = {sid: s_before_total.get(sid, 0.0) * factor for sid in s_before_total.keys()}

        return s_before_total, s_after_total

    def _build_per_world_plans(
        self,
        ctx: MultiWorldRebalanceContext,
        per_world_positions: Mapping[str, List[PositionSlice]],
    ) -> Dict[str, RebalancePlan]:
        plans: Dict[str, RebalancePlan] = {}
        for wid, positions in per_world_positions.items():
            gw_before = ctx.world_alloc_before.get(wid, 0.0)
            gw_after = ctx.world_alloc_after.get(wid, 0.0)
            s_before_total, s_after_total = self._derive_strategy_targets(ctx, wid, positions)
            single_ctx = RebalanceContext(
                total_equity=ctx.total_equity,
                world_id=wid,
                world_alloc_before=gw_before,
                world_alloc_after=gw_after,
                strategy_alloc_before=s_before_total,
                strategy_alloc_after=s_after_total,
                positions=positions,
                min_trade_notional=ctx.min_trade_notional,
                lot_size_by_symbol=ctx.lot_size_by_symbol,
            )
            plans[wid] = self._single.plan(single_ctx)
        return plans

    def _build_global_deltas(
        self,
        ctx: MultiWorldRebalanceContext,
        per_world_positions: Mapping[str, List[PositionSlice]],
        per_world_plans: Mapping[str, RebalancePlan],
    ) -> List[SymbolDelta]:
        agg_notional: Dict[Tuple[str | None, str], float] = {}
        marks_cache: Dict[Tuple[str | None, str], List[float]] = {}

        for wid, positions in per_world_positions.items():
            plan = per_world_plans[wid]
            for delta in plan.deltas:
                key = (delta.venue, delta.symbol)
                marks = [
                    pos.mark
                    for pos in positions
                    if pos.symbol == delta.symbol and pos.venue == delta.venue and pos.mark > 0
                ]
                if not marks:
                    continue
                avg_mark = sum(marks) / len(marks)
                agg_notional[key] = agg_notional.get(key, 0.0) + delta.delta_qty * avg_mark
                marks_cache.setdefault(key, []).append(avg_mark)

        global_deltas: List[SymbolDelta] = []
        for key, d_notional in agg_notional.items():
            if abs(d_notional) < (ctx.min_trade_notional or 0.0):
                continue
            marks = marks_cache.get(key, [1.0])
            avg_mark = sum(marks) / max(len(marks), 1)
            delta_qty = 0.0 if avg_mark == 0 else d_notional / avg_mark
            if delta_qty != 0.0:
                venue, symbol = key
                global_deltas.append(SymbolDelta(symbol=symbol, delta_qty=delta_qty, venue=venue))

        return global_deltas

