from __future__ import annotations

from typing import Dict, List

from fastapi import APIRouter

from ..rebalancing import (
    MultiWorldProportionalRebalancer,
    MultiWorldRebalanceContext,
    PositionSlice,
)
from ..schemas import (
    MultiWorldRebalanceRequest,
    MultiWorldRebalanceResponse,
    PositionSliceModel,
    RebalancePlanModel,
    SymbolDeltaModel,
)
from ..services import WorldService
from . import rebalancing as _unused  # ensure package init
from .overlay import OverlayPlanner
from ..services import WorldService


def _convert_positions(models: List[PositionSliceModel]) -> List[PositionSlice]:
    return [
        PositionSlice(
            world_id=m.world_id,
            strategy_id=m.strategy_id,
            symbol=m.symbol,
            qty=m.qty,
            mark=m.mark,
            venue=m.venue,
        )
        for m in models
    ]


def _serialize_plan(plan) -> Dict[str, RebalancePlanModel]:
    out: Dict[str, RebalancePlanModel] = {}
    for wid, p in plan.items():
        out[wid] = RebalancePlanModel(
            world_id=wid,
            scale_world=p.scale_world,
            scale_by_strategy=dict(p.scale_by_strategy),
            deltas=[
                SymbolDeltaModel(symbol=d.symbol, delta_qty=d.delta_qty, venue=d.venue)
                for d in p.deltas
            ],
        )
    return out


def create_rebalancing_router(service: WorldService) -> APIRouter:
    router = APIRouter()

    @router.post('/rebalancing/plan', response_model=MultiWorldRebalanceResponse)
    async def post_rebalance_plan(payload: MultiWorldRebalanceRequest) -> MultiWorldRebalanceResponse:
        # Build context from request
        ctx = MultiWorldRebalanceContext(
            total_equity=payload.total_equity,
            world_alloc_before=payload.world_alloc_before,
            world_alloc_after=payload.world_alloc_after,
            strategy_alloc_before_total=payload.strategy_alloc_before_total,
            strategy_alloc_after_total=payload.strategy_alloc_after_total,
            positions=_convert_positions(payload.positions),
            min_trade_notional=payload.min_trade_notional or 0.0,
            lot_size_by_symbol=payload.lot_size_by_symbol,
        )

        planner = MultiWorldProportionalRebalancer()
        result = planner.plan(ctx)

        per_world = _serialize_plan(result.per_world)
        global_deltas = [
            SymbolDeltaModel(symbol=d.symbol, delta_qty=d.delta_qty, venue=d.venue)
            for d in result.global_deltas
        ]
        mode = (payload.mode or 'scaling').lower()
        if mode in ('overlay', 'hybrid'):
            raise NotImplementedError(
                "Overlay mode is not implemented yet. Use mode='scaling'."
            )
        return MultiWorldRebalanceResponse(per_world=per_world, global_deltas=global_deltas)

    @router.post('/rebalancing/apply', response_model=MultiWorldRebalanceResponse)
    async def post_rebalance_apply(payload: MultiWorldRebalanceRequest) -> MultiWorldRebalanceResponse:
        # Compute plan (same as /plan)
        ctx = MultiWorldRebalanceContext(
            total_equity=payload.total_equity,
            world_alloc_before=payload.world_alloc_before,
            world_alloc_after=payload.world_alloc_after,
            strategy_alloc_before_total=payload.strategy_alloc_before_total,
            strategy_alloc_after_total=payload.strategy_alloc_after_total,
            positions=_convert_positions(payload.positions),
            min_trade_notional=payload.min_trade_notional or 0.0,
            lot_size_by_symbol=payload.lot_size_by_symbol,
        )
        planner = MultiWorldProportionalRebalancer()
        result = planner.plan(ctx)

        per_world = _serialize_plan(result.per_world)
        global_deltas = [
            SymbolDeltaModel(symbol=d.symbol, delta_qty=d.delta_qty, venue=d.venue)
            for d in result.global_deltas
        ]

        mode = (payload.mode or 'scaling').lower()
        if mode in ('overlay', 'hybrid'):
            raise NotImplementedError(
                "Overlay mode is not implemented yet. Use mode='scaling'."
            )

        # Persist a compact audit entry per world (and a summary)
        try:
            await service.store.record_rebalance_plan({
                "per_world": {wid: per_world[wid].model_dump() for wid in per_world.keys()},
                "global_deltas": [g.model_dump() for g in global_deltas],
                **({"overlay_deltas": [d.model_dump() for d in overlay_deltas]} if overlay_deltas else {}),
            })
        except Exception:
            # Storage is best-effort for apply
            pass

        # Emit a ControlBus event per world if a bus is configured
        if getattr(service, "bus", None) is not None:
            bus = service.bus
            try:
                for wid, plan in per_world.items():
                    await bus.publish_rebalancing_plan(
                        wid,
                        {
                            "scale_world": plan.scale_world,
                            "scale_by_strategy": plan.scale_by_strategy,
                            "deltas": [d.model_dump() for d in plan.deltas],
                        },
                        version=1,
                    )
            except Exception:
                # Non-fatal if bus is unavailable
                pass

        return MultiWorldRebalanceResponse(per_world=per_world, global_deltas=global_deltas)

    return router
