from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Mapping, Optional, Protocol, Tuple


@dataclass
class PositionSlice:
    """Minimal, broker-agnostic view of a position row.

    This intentionally mirrors the ``PortfolioSnapshot`` schema from
    ``qmtl.foundation.schema.order_events`` while allowing an optional
    venue/exchange dimension to support centralized venue-aware netting.
    """

    world_id: str
    symbol: str
    qty: float
    mark: float
    strategy_id: str
    venue: str | None = None  # optional exchange/broker identifier

    @property
    def notional(self) -> float:
        return self.qty * self.mark


@dataclass
class RebalanceContext:
    """Inputs required to compute a rebalance plan for a world.

    Attributes
    ----------
    total_equity:
        Total portfolio equity across all worlds (base currency).
    world_id:
        Target world identifier.
    world_alloc_before/world_alloc_after:
        Allocation ratios (0.0–1.0) relative to ``total_equity``.
    strategy_alloc_before/strategy_alloc_after:
        Per-strategy allocation ratios (0.0–1.0) relative to ``total_equity``.
        The rebalancer combines both world- and strategy-level changes.
    positions:
        Flattened position rows for all strategies in the world.
    min_trade_notional:
        Floor for emitting a trade to avoid fee churn.
    lot_size_by_symbol:
        Optional lot sizing map for rounding quantities.
    """

    total_equity: float
    world_id: str
    world_alloc_before: float
    world_alloc_after: float
    strategy_alloc_before: Mapping[str, float]
    strategy_alloc_after: Mapping[str, float]
    positions: List[PositionSlice]
    min_trade_notional: float = 0.0
    lot_size_by_symbol: Mapping[str, float] | None = None


@dataclass
class SymbolDelta:
    """Aggregated delta required per (venue, symbol).

    The planner emits signed ``delta_qty`` to move current holdings toward
    the new allocation. Positive increases exposure; negative reduces.
    """

    symbol: str
    delta_qty: float
    venue: str | None = None


@dataclass
class RebalancePlan:
    world_id: str
    scale_world: float
    scale_by_strategy: Dict[str, float]
    deltas: List[SymbolDelta] = field(default_factory=list)


class Rebalancer(Protocol):
    """Pluggable rebalancer interface.

    Implementations should be deterministic and side-effect free: they return
    a plan that can be fed to an execution layer capable of position-based
    reconciliation (e.g., reduce-only where applicable) without requiring
    order state introspection.
    """

    def plan(self, ctx: RebalanceContext) -> RebalancePlan:
        ...
