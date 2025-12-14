from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from ..policy_engine import Policy
from ..schemas import (
    ApplyPlan,
    ApplyRequest,
    EvaluationOverride,
    EvaluationRunModel,
    LivePromotionApproveRequest,
    LivePromotionApplyRequest,
    LivePromotionAutoApplyResponse,
    LivePromotionPlanResponse,
    LivePromotionRejectRequest,
)
from ..services import WorldService


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_iso(ts: str) -> datetime:
    candidate = str(ts or "").strip()
    if not candidate:
        return datetime.min.replace(tzinfo=timezone.utc)
    if candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(candidate)
    except Exception:
        return datetime.min.replace(tzinfo=timezone.utc)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _extract_live_promotion_mode(policy: object) -> str | None:
    if isinstance(policy, Policy):
        governance = policy.governance
        if governance and governance.live_promotion:
            return str(governance.live_promotion.mode)
        return None
    if isinstance(policy, dict):
        governance = policy.get("governance")
        if not isinstance(governance, dict):
            return None
        live_promotion = governance.get("live_promotion")
        if not isinstance(live_promotion, dict):
            return None
        mode = live_promotion.get("mode")
        return str(mode) if mode is not None else None
    return None


async def _get_live_promotion_mode(service: WorldService, world_id: str) -> str | None:
    policy = await service.store.get_default_policy(world_id)
    return _extract_live_promotion_mode(policy)


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
        mode = await _get_live_promotion_mode(service, world_id)
        if str(mode or "").lower() == "disabled":
            raise HTTPException(status_code=409, detail="live promotion is disabled by policy")
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
        mode = await _get_live_promotion_mode(service, world_id)
        if str(mode or "").lower() == "disabled":
            raise HTTPException(status_code=409, detail="live promotion is disabled by policy")
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

    @router.post(
        "/worlds/{world_id}/promotions/live/apply",
        response_model=EvaluationRunModel,
    )
    async def post_live_promotion_apply(
        world_id: str,
        payload: LivePromotionApplyRequest,
    ) -> EvaluationRunModel:
        mode = await _get_live_promotion_mode(service, world_id)
        mode_normalized = str(mode or "").lower()
        if mode_normalized == "disabled":
            raise HTTPException(status_code=409, detail="live promotion is disabled by policy")

        record = await service.store.get_evaluation_run(world_id, payload.strategy_id, payload.run_id)
        if record is None:
            raise HTTPException(status_code=404, detail="evaluation run not found")

        summary = record.get("summary") if isinstance(record, dict) else None
        if not isinstance(summary, dict):
            raise HTTPException(status_code=422, detail="evaluation run missing summary")

        override_status = str(summary.get("override_status") or "none").lower()
        if mode_normalized == "manual_approval" and override_status != "approved" and not payload.force:
            raise HTTPException(status_code=409, detail="manual approval required before applying live promotion")

        plan_resp = await get_live_promotion_plan(
            world_id,
            strategy_id=payload.strategy_id,
            run_id=payload.run_id,
        )
        apply_payload = ApplyRequest(
            run_id=payload.apply_run_id,
            plan=plan_resp.plan,
        )
        await service.apply(world_id, apply_payload, gating=None)
        updated = await service.store.get_evaluation_run(world_id, payload.strategy_id, payload.run_id)
        if updated is None:
            raise HTTPException(status_code=404, detail="evaluation run not found")
        return EvaluationRunModel(**updated)

    @router.post(
        "/worlds/{world_id}/promotions/live/auto-apply",
        response_model=LivePromotionAutoApplyResponse,
    )
    async def post_live_promotion_auto_apply(world_id: str) -> LivePromotionAutoApplyResponse:
        mode = await _get_live_promotion_mode(service, world_id)
        mode_normalized = str(mode or "").lower()
        if mode_normalized != "auto_apply":
            raise HTTPException(status_code=409, detail="live promotion auto-apply is not enabled by policy")

        runs = await service.store.list_evaluation_runs(world_id=world_id)
        if not runs:
            return LivePromotionAutoApplyResponse(world_id=world_id, applied=False)

        def _rank(run: dict) -> tuple[datetime, datetime]:
            created = _parse_iso(str(run.get("created_at") or ""))
            updated = _parse_iso(str(run.get("updated_at") or "")) or created
            return updated, created

        # Choose the freshest paper-stage evaluation run as the source of truth.
        paper_runs: list[dict] = [
            r
            for r in runs
            if isinstance(r, dict) and str(r.get("stage") or "").lower() == "paper"
        ]
        candidate_runs = paper_runs or [r for r in runs if isinstance(r, dict)]
        if not candidate_runs:
            return LivePromotionAutoApplyResponse(world_id=world_id, applied=False)

        source = max(candidate_runs, key=_rank)
        strategy_id = str(source.get("strategy_id") or "")
        run_id = str(source.get("run_id") or "")
        if not strategy_id or not run_id:
            return LivePromotionAutoApplyResponse(world_id=world_id, applied=False)

        plan_resp = await get_live_promotion_plan(world_id, strategy_id=strategy_id, run_id=run_id)
        apply_run_id = f"auto-live-{run_id}-{_utc_now_iso().replace(':', '').replace('-', '')}"
        apply_payload = ApplyRequest(
            run_id=apply_run_id,
            plan=plan_resp.plan,
        )
        await service.apply(world_id, apply_payload, gating=None)
        return LivePromotionAutoApplyResponse(
            world_id=world_id,
            applied=True,
            source_strategy_id=strategy_id,
            source_run_id=run_id,
            apply_run_id=apply_run_id,
            plan=plan_resp.plan,
        )

    return router
