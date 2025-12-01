from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping

from .base import PositionSlice, RebalancePlan


@dataclass
class ExecutionDelta:
    """Per-strategy execution unit derived from a world rebalance plan.

    Positive ``delta_qty`` increases exposure; negative reduces. This structure
    is strategy-aware and can be translated into broker-native orders by the
    execution layer (e.g., reduce-only for negative deltas where supported).
    """

    world_id: str
    strategy_id: str
    symbol: str
    delta_qty: float
    venue: str | None = None


def allocate_strategy_deltas(
    world_id: str,
    plan: RebalancePlan,
    positions: List[PositionSlice],
    *,
    mode: str = "proportional-existing",
    fallback_weights: Mapping[str, float] | None = None,
) -> List[ExecutionDelta]:
    """Split aggregated per-(venue,symbol) deltas back to strategies.

    Parameters
    ----------
    world_id:
        Target world id.
    plan:
        World-level rebalance plan with aggregated deltas.
    positions:
        Positions used for planning; must include ``strategy_id``.
    mode:
        - "proportional-existing" (default): distribute by existing absolute
          notional per (venue, symbol). If no existing exposure and delta > 0,
          fall back to ``fallback_weights`` if provided; otherwise skip.
    fallback_weights:
        Optional strategy weights (sum to 1.0) on total-equity basis for cases
        where there is no existing exposure but a positive delta must be opened.

    Notes
    -----
    - This adapter is intentionally conservative: opening new per-symbol
      exposures without prior holdings requires explicit ``fallback_weights``.
    - Execution policy (reduce-only, flatten-then-open) lives in the execution
      layer; this function only apportions quantities to strategies.
    """

    bucket = _build_notional_index(world_id, positions)

    out: List[ExecutionDelta] = []
    for d in plan.deltas:
        key = (d.venue, d.symbol)
        strat_notional = bucket.get(key, {})
        if strat_notional:
            out.extend(
                _allocate_existing_delta(world_id, d.symbol, d.delta_qty, d.venue, strat_notional)
            )
            continue
        out.extend(
            _allocate_fallback_delta(world_id, d.symbol, d.delta_qty, d.venue, fallback_weights)
        )

    return out


def _build_notional_index(
    world_id: str, positions: Iterable[PositionSlice]
) -> Dict[tuple[str | None, str], Dict[str, float]]:
    bucket: Dict[tuple[str | None, str], Dict[str, float]] = {}
    for pos in positions:
        if pos.world_id != world_id:
            continue
        key = (pos.venue, pos.symbol)
        slot = bucket.setdefault(key, {})
        slot[pos.strategy_id] = slot.get(pos.strategy_id, 0.0) + abs(pos.qty * pos.mark)
    return bucket


def _allocate_existing_delta(
    world_id: str,
    symbol: str,
    delta_qty: float,
    venue: str | None,
    strat_notional: Mapping[str, float],
) -> List[ExecutionDelta]:
    total = sum(strat_notional.values())
    if total <= 0:
        return []
    allocations: List[ExecutionDelta] = []
    for sid, notional in strat_notional.items():
        share = notional / total if total else 0.0
        qty = delta_qty * share
        if qty != 0.0:
            allocations.append(
                ExecutionDelta(
                    world_id=world_id,
                    strategy_id=sid,
                    symbol=symbol,
                    delta_qty=qty,
                    venue=venue,
                )
            )
    return allocations


def _allocate_fallback_delta(
    world_id: str,
    symbol: str,
    delta_qty: float,
    venue: str | None,
    fallback_weights: Mapping[str, float] | None,
) -> List[ExecutionDelta]:
    if delta_qty <= 0 or not fallback_weights:
        return []
    total_w = sum(max(0.0, w) for w in fallback_weights.values())
    if total_w <= 0:
        return []
    allocations: List[ExecutionDelta] = []
    for sid, weight in fallback_weights.items():
        share = max(0.0, weight) / total_w
        qty = delta_qty * share
        if qty != 0.0:
            allocations.append(
                ExecutionDelta(
                    world_id=world_id,
                    strategy_id=sid,
                    symbol=symbol,
                    delta_qty=qty,
                    venue=venue,
                )
            )
    return allocations
