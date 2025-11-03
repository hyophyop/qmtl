from __future__ import annotations

"""Helpers to translate world rebalancing plans into order payloads.

These helpers do not submit orders. They convert per-world ``RebalancePlan``
or strategy-split deltas into order-shaped dictionaries that existing
publishing paths can consume.
"""

from dataclasses import dataclass
from typing import Iterable, List, Mapping, Sequence

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


def _build_order(symbol: str, qty: float, *, reduce_only: bool, tif: str) -> dict:
    side = "buy" if qty >= 0 else "sell"
    return {
        "symbol": symbol,
        "quantity": qty,
        "side": side,
        "time_in_force": tif,
        **({"reduce_only": True} if reduce_only else {}),
    }


def orders_from_world_plan(plan: RebalancePlan, *, options: OrderOptions | None = None) -> List[dict]:
    """Convert a per-world ``RebalancePlan`` into order payloads.

    Negative deltas become reduce-only orders (when ``reduce_only_for_negative`` is
    True) to enforce non-increasing exposure on cuts.
    """
    opts = options or OrderOptions()
    orders: List[dict] = []
    for d in plan.deltas:
        reduce_only = bool(opts.reduce_only_for_negative and d.delta_qty < 0)
        orders.append(
            _build_order(d.symbol, d.delta_qty, reduce_only=reduce_only, tif=opts.time_in_force)
        )
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
        orders.append(
            _build_order(d.symbol, d.delta_qty, reduce_only=reduce_only, tif=opts.time_in_force)
        )
    return orders


def orders_from_symbol_deltas(
    deltas: Sequence[SymbolDelta], *, options: OrderOptions | None = None
) -> List[dict]:
    """Convert aggregated symbol deltas (global view) into order payloads."""
    opts = options or OrderOptions()
    orders: List[dict] = []
    for d in deltas:
        reduce_only = bool(opts.reduce_only_for_negative and d.delta_qty < 0)
        orders.append(
            _build_order(d.symbol, d.delta_qty, reduce_only=reduce_only, tif=opts.time_in_force)
        )
    return orders


__all__ = [
    "OrderOptions",
    "orders_from_world_plan",
    "orders_from_strategy_deltas",
    "orders_from_symbol_deltas",
]
