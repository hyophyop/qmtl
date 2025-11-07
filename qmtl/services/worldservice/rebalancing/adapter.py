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

    # Index positions by (venue, symbol) -> strategy -> abs(notional)
    bucket: Dict[tuple[str | None, str], Dict[str, float]] = {}
    for p in positions:
        if p.world_id != world_id:
            continue
        key = (p.venue, p.symbol)
        b = bucket.setdefault(key, {})
        b[p.strategy_id] = b.get(p.strategy_id, 0.0) + abs(p.qty * p.mark)

    out: List[ExecutionDelta] = []
    for d in plan.deltas:
        key = (d.venue, d.symbol)
        strat_notional = bucket.get(key, {})
        total = sum(strat_notional.values())

        if total > 0:
            # Distribute by existing absolute notional
            for sid, n in strat_notional.items():
                share = 0.0 if total == 0 else (n / total)
                qty = d.delta_qty * share
                if qty != 0.0:
                    out.append(
                        ExecutionDelta(
                            world_id=world_id,
                            strategy_id=sid,
                            symbol=d.symbol,
                            delta_qty=qty,
                            venue=d.venue,
                        )
                    )
        else:
            # No existing exposure. For reductions, nothing to do. For increases,
            # require fallback weights to avoid arbitrary assignment.
            if d.delta_qty <= 0:
                continue
            if fallback_weights:
                total_w = sum(max(0.0, w) for w in fallback_weights.values())
                if total_w <= 0:
                    continue
                for sid, w in fallback_weights.items():
                    share = max(0.0, w) / total_w
                    qty = d.delta_qty * share
                    if qty != 0.0:
                        out.append(
                            ExecutionDelta(
                                world_id=world_id,
                                strategy_id=sid,
                                symbol=d.symbol,
                                delta_qty=qty,
                                venue=d.venue,
                            )
                        )

    return out

