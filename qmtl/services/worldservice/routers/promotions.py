from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from ..schemas import (
    ApplyPlan,
    EvaluationOverride,
    EvaluationRunModel,
    LivePromotionApproveRequest,
    LivePromotionPlanResponse,
    LivePromotionRejectRequest,
)
from ..services import WorldService


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def create_promotions_router(service: WorldService) -> APIRouter:
    router = APIRouter()

    @router.post(
        "/worlds/{world_id}/promotions/live/approve",
        response_model=EvaluationRunModel,
    )
    async def post_live_promotion_approve(
        world_id: str,
        payload: LivePromotionApproveRequest,
    ) -> EvaluationRunModel:
        override = EvaluationOverride(
            status="approved",
            reason=payload.reason,
            actor=payload.actor,
            timestamp=payload.timestamp or _utc_now_iso(),
        )
        record = await service.record_evaluation_override(
            world_id,
            payload.strategy_id,
            payload.run_id,
            override,
        )
        return EvaluationRunModel(**record)

    @router.post(
        "/worlds/{world_id}/promotions/live/reject",
        response_model=EvaluationRunModel,
    )
    async def post_live_promotion_reject(
        world_id: str,
        payload: LivePromotionRejectRequest,
    ) -> EvaluationRunModel:
        override = EvaluationOverride(
            status="rejected",
            reason=payload.reason,
            actor=payload.actor,
            timestamp=payload.timestamp or _utc_now_iso(),
        )
        record = await service.record_evaluation_override(
            world_id,
            payload.strategy_id,
            payload.run_id,
            override,
        )
        return EvaluationRunModel(**record)

    @router.get(
        "/worlds/{world_id}/promotions/live/plan",
        response_model=LivePromotionPlanResponse,
    )
    async def get_live_promotion_plan(
        world_id: str,
        *,
        strategy_id: str,
        run_id: str,
    ) -> LivePromotionPlanResponse:
        record = await service.store.get_evaluation_run(world_id, strategy_id, run_id)
        if record is None:
            raise HTTPException(status_code=404, detail="evaluation run not found")

        summary = record.get("summary") if isinstance(record, dict) else None
        if not isinstance(summary, dict):
            raise HTTPException(status_code=422, detail="evaluation run missing summary")

        target_active = summary.get("active_set")
        if not isinstance(target_active, list) or not all(isinstance(v, str) for v in target_active):
            raise HTTPException(status_code=422, detail="evaluation run missing summary.active_set")

        current_active = await service.store.get_decisions(world_id)
        current_set = {str(v) for v in current_active if str(v).strip()}
        target_set = {str(v) for v in target_active if str(v).strip()}

        plan = ApplyPlan(
            activate=sorted(target_set - current_set),
            deactivate=sorted(current_set - target_set),
        )
        return LivePromotionPlanResponse(
            world_id=world_id,
            strategy_id=strategy_id,
            run_id=run_id,
            plan=plan,
            target_active=sorted(target_set),
            current_active=sorted(current_set),
        )

    return router
