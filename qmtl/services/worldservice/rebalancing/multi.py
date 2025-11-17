from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Mapping, Optional

from .base import (
    PositionSlice,
    RebalancePlan,
    Rebalancer,
    RebalanceContext,
    SymbolDelta,
)
from .rule_based import ProportionalRebalancer
from .calculators import (
    GlobalDeltaAggregator,
    StrategyAllocationCalculator,
)


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
    positions: List[PositionSlice] = field(default_factory=list)
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

    def _build_per_world_plans(
        self,
        ctx: MultiWorldRebalanceContext,
        per_world_positions: Mapping[str, List[PositionSlice]],
    ) -> Dict[str, RebalancePlan]:
        calculator = StrategyAllocationCalculator(ctx)
        plans: Dict[str, RebalancePlan] = {}
        for wid, positions in per_world_positions.items():
            targets = calculator.derive(wid, positions)
            single_ctx = RebalanceContext(
                total_equity=ctx.total_equity,
                world_id=wid,
                world_alloc_before=ctx.world_alloc_before.get(wid, 0.0),
                world_alloc_after=ctx.world_alloc_after.get(wid, 0.0),
                strategy_alloc_before=dict(targets.before),
                strategy_alloc_after=dict(targets.after),
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
        aggregator = GlobalDeltaAggregator(ctx)
        for wid, positions in per_world_positions.items():
            aggregator.ingest(positions, per_world_plans[wid])
        return aggregator.build()

