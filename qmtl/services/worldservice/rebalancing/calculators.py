"""Reusable calculators that support multi-world rebalancing orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping, MutableMapping, Tuple, TYPE_CHECKING

from .base import PositionSlice, RebalancePlan, SymbolDelta

if TYPE_CHECKING:  # pragma: no cover - for typing only
    from .multi import MultiWorldRebalanceContext


@dataclass(frozen=True)
class StrategyAllocationTargets:
    """Pair of total-equity allocation ratios before/after a rebalance."""

    before: Mapping[str, float]
    after: Mapping[str, float]


class StrategyAllocationCalculator:
    """Derive strategy allocation targets for a world within a rebalance."""

    def __init__(self, ctx: "MultiWorldRebalanceContext") -> None:
        self._ctx = ctx

    def derive(self, world_id: str, positions: Iterable[PositionSlice]) -> StrategyAllocationTargets:
        snapshot = list(positions)
        before = self._resolve_before(world_id, snapshot)
        after = self._resolve_after(world_id, before)
        return StrategyAllocationTargets(before=before, after=after)

    def _resolve_before(
        self, world_id: str, positions: List[PositionSlice]
    ) -> MutableMapping[str, float]:
        explicit = (self._ctx.strategy_alloc_before_total or {}).get(world_id)
        if explicit is not None:
            return dict(explicit)
        totals: Dict[str, float] = {}
        world_total = 0.0
        for pos in positions:
            notional = pos.qty * pos.mark
            totals[pos.strategy_id] = totals.get(pos.strategy_id, 0.0) + notional
            world_total += notional
        if world_total <= 0.0:
            return {key: 0.0 for key in totals}
        denom = self._ctx.total_equity if self._ctx.total_equity > 0 else world_total
        return {sid: value / denom for sid, value in totals.items()}

    def _resolve_after(
        self, world_id: str, before: Mapping[str, float]
    ) -> MutableMapping[str, float]:
        explicit = (self._ctx.strategy_alloc_after_total or {}).get(world_id)
        if explicit is not None:
            return dict(explicit)
        factor = self._scale_factor(world_id)
        return {sid: before.get(sid, 0.0) * factor for sid in before.keys()}

    def _scale_factor(self, world_id: str) -> float:
        gw_before = self._ctx.world_alloc_before.get(world_id, 0.0)
        gw_after = self._ctx.world_alloc_after.get(world_id, 0.0)
        if gw_before > 0:
            return gw_after / gw_before
        return 1.0 if gw_after > 0 else 0.0


class GlobalDeltaAggregator:
    """Aggregate per-world deltas into a global cross-world view."""

    def __init__(self, ctx: "MultiWorldRebalanceContext") -> None:
        self._ctx = ctx
        self._agg_notional: Dict[Tuple[str | None, str], float] = {}
        self._marks: Dict[Tuple[str | None, str], List[float]] = {}

    def ingest(
        self,
        positions: Iterable[PositionSlice],
        plan: RebalancePlan,
    ) -> None:
        snapshot = list(positions)
        for delta in plan.deltas:
            key = (delta.venue, delta.symbol)
            marks = [
                pos.mark
                for pos in snapshot
                if pos.symbol == delta.symbol and pos.venue == delta.venue and pos.mark > 0
            ]
            if not marks:
                continue
            avg_mark = sum(marks) / len(marks)
            self._agg_notional[key] = self._agg_notional.get(key, 0.0) + delta.delta_qty * avg_mark
            self._marks.setdefault(key, []).append(avg_mark)

    def build(self) -> List[SymbolDelta]:
        deltas: List[SymbolDelta] = []
        threshold = self._ctx.min_trade_notional or 0.0
        for key, notional in self._agg_notional.items():
            if abs(notional) < threshold:
                continue
            marks = self._marks.get(key, [1.0])
            avg_mark = sum(marks) / max(len(marks), 1)
            delta_qty = 0.0 if avg_mark == 0 else notional / avg_mark
            if delta_qty == 0.0:
                continue
            venue, symbol = key
            deltas.append(SymbolDelta(symbol=symbol, delta_qty=delta_qty, venue=venue))
        return deltas

