from __future__ import annotations

from typing import Dict, List

from fastapi import APIRouter, HTTPException

from ..rebalancing import (
    MultiWorldProportionalRebalancer,
    MultiWorldRebalanceContext,
    PositionSlice,
)
from ..alpha_metrics import build_alpha_metrics_envelope
from ..schemas import (
    AlphaMetricsEnvelope,
    MultiWorldRebalanceRequest,
    MultiWorldRebalanceResponse,
    PositionSliceModel,
    RebalancePlanModel,
    SymbolDeltaModel,
)
from ..services import WorldService
from . import rebalancing as _unused  # ensure package init


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


def _serialize_plan_models(plan) -> Dict[str, RebalancePlanModel]:
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


def create_rebalancing_router(
    service: WorldService,
    *,
    compat_rebalance_v2: bool = False,
    alpha_metrics_required: bool = False,
) -> APIRouter:
    router = APIRouter()
    max_supported_version = 2 if compat_rebalance_v2 else 1

    def _negotiate_version(requested: int | None) -> int:
        version = requested or 1
        if version < 1:
            version = 1
        return min(version, max_supported_version)

    def _build_response_payload(result, active_version: int) -> tuple[MultiWorldRebalanceResponse, AlphaMetricsEnvelope | None, Dict[str, RebalancePlanModel], List[SymbolDeltaModel]]:
        per_world = _serialize_plan_models(result.per_world)
        global_deltas = [
            SymbolDeltaModel(symbol=d.symbol, delta_qty=d.delta_qty, venue=d.venue)
            for d in result.global_deltas
        ]
        alpha_metrics = build_alpha_metrics_envelope(per_world) if active_version >= 2 else None
        response_kwargs: dict[str, object] = {
            "schema_version": active_version,
            "per_world": per_world,
            "global_deltas": global_deltas,
        }
        if alpha_metrics is not None:
            response_kwargs["alpha_metrics"] = alpha_metrics
        return MultiWorldRebalanceResponse(**response_kwargs), alpha_metrics, per_world, global_deltas

    def _ensure_mode(payload: MultiWorldRebalanceRequest) -> None:
        mode = (payload.mode or "scaling").lower()
        if mode in ("overlay", "hybrid"):
            raise HTTPException(
                status_code=501,
                detail="Overlay mode is not implemented yet. Use mode='scaling'.",
            )

    def _ensure_version_requirements(requested_version: int | None) -> None:
        if alpha_metrics_required and (requested_version or 1) < 2:
            raise HTTPException(
                status_code=400,
                detail="schema_version>=2 required when alpha_metrics_required is enabled",
            )

    @router.post('/rebalancing/plan', response_model=MultiWorldRebalanceResponse)
    async def post_rebalance_plan(payload: MultiWorldRebalanceRequest) -> MultiWorldRebalanceResponse:
        _ensure_mode(payload)
        _ensure_version_requirements(payload.schema_version)
        active_version = _negotiate_version(payload.schema_version)
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

        response, _, _, _ = _build_response_payload(result, active_version)
        return response

    @router.post('/rebalancing/apply', response_model=MultiWorldRebalanceResponse)
    async def post_rebalance_apply(payload: MultiWorldRebalanceRequest) -> MultiWorldRebalanceResponse:
        _ensure_mode(payload)
        _ensure_version_requirements(payload.schema_version)
        active_version = _negotiate_version(payload.schema_version)
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

        response, alpha_metrics, per_world, global_deltas = _build_response_payload(
            result, active_version
        )
        overlay_deltas: list[SymbolDeltaModel] | None = None

        # Persist a compact audit entry per world (and a summary)
        plan_payload = service._serialize_plan(
            result,
            schema_version=active_version,
            alpha_metrics=alpha_metrics.model_dump() if alpha_metrics is not None else None,
        )
        payload_to_store = dict(plan_payload)

        try:
            if overlay_deltas is not None:
                payload_to_store["overlay_deltas"] = [d.model_dump() for d in overlay_deltas]

            await service.store.record_rebalance_plan(payload_to_store)
        except Exception:
            # Storage is best-effort for apply
            pass

        # Emit a ControlBus event per world if a bus is configured
        if getattr(service, "bus", None) is not None:
            bus = service.bus
            try:
                for wid in per_world.keys():
                    plan_payload = payload_to_store["per_world"][wid]
                    await bus.publish_rebalancing_plan(
                        wid,
                        plan_payload,
                        version=active_version,
                    )
            except Exception:
                # Non-fatal if bus is unavailable
                pass

        response_kwargs: dict[str, object] = {
            "schema_version": active_version,
            "per_world": per_world,
            "global_deltas": global_deltas,
        }
        if overlay_deltas is not None:
            response_kwargs["overlay_deltas"] = overlay_deltas
        if alpha_metrics is not None:
            response_kwargs["alpha_metrics"] = alpha_metrics

        return MultiWorldRebalanceResponse(**response_kwargs)

    return router
