from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import inspect
import re

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
    LivePromotionCandidate,
    LivePromotionCandidatesResponse,
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


@dataclass(frozen=True, slots=True)
class LivePromotionGovernance:
    mode: str | None
    cooldown: str | None
    max_live_slots: int | None
    canary_fraction: float | None
    approvers: list[str] | None


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


def _extract_live_promotion_governance(policy: object) -> LivePromotionGovernance:
    if isinstance(policy, Policy):
        governance = policy.governance
        live_promotion = governance.live_promotion if governance else None
        if live_promotion is None:
            return LivePromotionGovernance(None, None, None, None, None)
        return LivePromotionGovernance(
            mode=str(live_promotion.mode),
            cooldown=live_promotion.cooldown,
            max_live_slots=live_promotion.max_live_slots,
            canary_fraction=live_promotion.canary_fraction,
            approvers=list(live_promotion.approvers) if live_promotion.approvers is not None else None,
        )
    if isinstance(policy, dict):
        def _coerce_int(value: object) -> int | None:
            if value is None:
                return None
            try:
                return int(value)
            except Exception:
                return None

        def _coerce_float(value: object) -> float | None:
            if value is None:
                return None
            try:
                return float(value)
            except Exception:
                return None

        governance = policy.get("governance")
        if not isinstance(governance, dict):
            return LivePromotionGovernance(None, None, None, None, None)
        live_promotion = governance.get("live_promotion")
        if not isinstance(live_promotion, dict):
            return LivePromotionGovernance(None, None, None, None, None)
        mode = live_promotion.get("mode")
        cooldown = live_promotion.get("cooldown")
        max_live_slots = live_promotion.get("max_live_slots")
        canary_fraction = live_promotion.get("canary_fraction")
        approvers = live_promotion.get("approvers")
        approver_list: list[str] | None = None
        if isinstance(approvers, list):
            approver_list = [str(v) for v in approvers if str(v).strip()]
        return LivePromotionGovernance(
            mode=str(mode) if mode is not None else None,
            cooldown=str(cooldown) if cooldown is not None else None,
            max_live_slots=_coerce_int(max_live_slots),
            canary_fraction=_coerce_float(canary_fraction),
            approvers=approver_list,
        )
    return LivePromotionGovernance(None, None, None, None, None)


async def _get_live_promotion_governance(service: WorldService, world_id: str) -> LivePromotionGovernance:
    policy = await service.store.get_default_policy(world_id)
    return _extract_live_promotion_governance(policy)


_DURATION_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*([smhd])\s*$", re.IGNORECASE)


def _parse_duration_seconds(value: str | None) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    match = _DURATION_RE.match(text)
    if not match:
        raise ValueError(f"invalid duration: {text!r}")
    amount = float(match.group(1))
    unit = match.group(2).lower()
    multiplier = {"s": 1, "m": 60, "h": 3600, "d": 86400}[unit]
    seconds = int(amount * multiplier)
    return max(0, seconds)


async def _last_completed_apply_ts(service: WorldService, world_id: str) -> datetime | None:
    entries = await service.store.get_audit(world_id)
    if not entries:
        return None
    best: datetime | None = None
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if str(entry.get("event") or "").lower() != "apply_stage":
            continue
        if str(entry.get("stage") or "").lower() != "completed":
            continue
        candidate = _parse_iso(str(entry.get("ts") or ""))
        if best is None or candidate > best:
            best = candidate
    if best is None or best == datetime.min.replace(tzinfo=timezone.utc):
        return None
    return best


async def _cooldown_remaining_seconds(
    service: WorldService,
    world_id: str,
    *,
    cooldown: str | None,
) -> int | None:
    try:
        cooldown_seconds = _parse_duration_seconds(cooldown)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if cooldown_seconds is None:
        return None
    last_completed = await _last_completed_apply_ts(service, world_id)
    if last_completed is None:
        return 0
    elapsed = max(0, int((datetime.now(timezone.utc) - last_completed).total_seconds()))
    return max(0, cooldown_seconds - elapsed)


def _stable_fraction_score(*, world_id: str, strategy_id: str, run_id: str) -> float:
    payload = f"{world_id}:{strategy_id}:{run_id}".encode()
    digest = hashlib.sha256(payload).digest()
    value = int.from_bytes(digest[:8], "big", signed=False)
    return value / float(1 << 64)


def _canary_allows(
    *,
    canary_fraction: float | None,
    world_id: str,
    strategy_id: str,
    run_id: str,
) -> bool:
    if canary_fraction is None:
        return True
    if canary_fraction <= 0:
        return False
    if canary_fraction >= 1:
        return True
    return _stable_fraction_score(world_id=world_id, strategy_id=strategy_id, run_id=run_id) < canary_fraction


async def _risk_snapshot_is_fresh(service: WorldService, world_id: str) -> bool:
    hub = getattr(service, "_risk_hub", None)
    if hub is None:
        return True
    getter = getattr(hub, "latest_snapshot", None)
    if getter is None:
        return True
    try:
        snap = getter(world_id)
        snap = await snap if inspect.isawaitable(snap) else snap
        return snap is not None
    except Exception:
        return False


def _summary_value(record: dict, key: str) -> str | None:
    summary = record.get("summary")
    if not isinstance(summary, dict):
        return None
    value = summary.get(key)
    if value is None:
        return None
    return str(value)


def _summary_status(record: dict) -> str:
    return str(_summary_value(record, "status") or "").lower()


async def _compute_promotion_block_reasons(
    service: WorldService,
    world_id: str,
    record: dict,
    *,
    governance: LivePromotionGovernance,
    override_status: str,
    target_active: list[str],
) -> list[str]:
    reasons: list[str] = []
    if str(governance.mode or "").lower() == "disabled":
        reasons.append("promotion_disabled")
    stage = str(record.get("stage") or "").lower()
    if stage != "paper":
        reasons.append("not_paper_stage")

    status = _summary_status(record)
    if status not in {"pass", "warn"}:
        reasons.append("validation_failed")

    if not await _risk_snapshot_is_fresh(service, world_id):
        reasons.append("risk_snapshot_missing_or_expired")

    cooldown_remaining = await _cooldown_remaining_seconds(service, world_id, cooldown=governance.cooldown)
    if (cooldown_remaining or 0) > 0:
        reasons.append("cooldown_active")

    if governance.max_live_slots is not None and len(target_active) > governance.max_live_slots:
        reasons.append("max_live_slots_exceeded")

    mode_normalized = str(governance.mode or "").lower()
    if mode_normalized == "manual_approval" and override_status != "approved":
        reasons.append("manual_approval_required")

    return reasons


def _ensure_actor_allowed(
    *,
    governance: LivePromotionGovernance,
    actor: str | None,
) -> None:
    if not governance.approvers:
        return
    actor_value = str(actor or "").strip()
    if not actor_value:
        raise HTTPException(status_code=422, detail="actor is required by policy")
    allowed = {str(v).strip() for v in governance.approvers if str(v).strip()}
    if actor_value not in allowed:
        raise HTTPException(status_code=403, detail="actor is not allowed by policy")


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
        governance = await _get_live_promotion_governance(service, world_id)
        mode_normalized = str(governance.mode or "").lower()
        if mode_normalized == "disabled":
            raise HTTPException(status_code=409, detail="live promotion is disabled by policy")
        _ensure_actor_allowed(governance=governance, actor=payload.actor)
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
        governance = await _get_live_promotion_governance(service, world_id)
        mode_normalized = str(governance.mode or "").lower()
        if mode_normalized == "disabled":
            raise HTTPException(status_code=409, detail="live promotion is disabled by policy")
        _ensure_actor_allowed(governance=governance, actor=payload.actor)
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

        governance = await _get_live_promotion_governance(service, world_id)
        mode_normalized = str(governance.mode or "").lower()
        override_status = str(summary.get("override_status") or "none").lower()
        cooldown_remaining_sec = await _cooldown_remaining_seconds(
            service,
            world_id,
            cooldown=governance.cooldown,
        )

        plan = ApplyPlan(
            activate=sorted(target_set - current_set),
            deactivate=sorted(current_set - target_set),
        )
        target_active_list = sorted(target_set)
        block_reasons = await _compute_promotion_block_reasons(
            service,
            world_id,
            record,
            governance=governance,
            override_status=override_status,
            target_active=target_active_list,
        )
        pending_manual_approval = block_reasons == ["manual_approval_required"]
        eligible = block_reasons in ([], ["manual_approval_required"])
        return LivePromotionPlanResponse(
            world_id=world_id,
            strategy_id=strategy_id,
            run_id=run_id,
            plan=plan,
            target_active=target_active_list,
            current_active=sorted(current_set),
            promotion_mode=governance.mode,
            override_status=override_status,
            pending_manual_approval=pending_manual_approval,
            eligible=eligible,
            blocked_reasons=block_reasons,
            cooldown_remaining_sec=cooldown_remaining_sec,
            max_live_slots=governance.max_live_slots,
            canary_fraction=governance.canary_fraction,
        )

    @router.post(
        "/worlds/{world_id}/promotions/live/apply",
        response_model=EvaluationRunModel,
    )
    async def post_live_promotion_apply(
        world_id: str,
        payload: LivePromotionApplyRequest,
    ) -> EvaluationRunModel:
        governance = await _get_live_promotion_governance(service, world_id)
        mode_normalized = str(governance.mode or "").lower()
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
        if "not_paper_stage" in plan_resp.blocked_reasons:
            raise HTTPException(status_code=409, detail="promotion requires paper-stage evaluation run")
        if "validation_failed" in plan_resp.blocked_reasons and not payload.force:
            raise HTTPException(status_code=409, detail="promotion requires passing validation")
        if "risk_snapshot_missing_or_expired" in plan_resp.blocked_reasons:
            raise HTTPException(status_code=409, detail="risk snapshot missing or expired")
        if "cooldown_active" in plan_resp.blocked_reasons:
            raise HTTPException(status_code=409, detail="cooldown active")
        if "max_live_slots_exceeded" in plan_resp.blocked_reasons:
            raise HTTPException(status_code=409, detail="max live slots exceeded")

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
        governance = await _get_live_promotion_governance(service, world_id)
        mode_normalized = str(governance.mode or "").lower()
        if mode_normalized != "auto_apply":
            raise HTTPException(status_code=409, detail="live promotion auto-apply is not enabled by policy")

        runs = await service.store.list_evaluation_runs(world_id=world_id)
        if not runs:
            return LivePromotionAutoApplyResponse(world_id=world_id, applied=False, reason="no_evaluation_runs")

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
        candidate_runs = paper_runs
        if not candidate_runs:
            return LivePromotionAutoApplyResponse(world_id=world_id, applied=False, reason="no_paper_runs")

        source = max(candidate_runs, key=_rank)
        strategy_id = str(source.get("strategy_id") or "")
        run_id = str(source.get("run_id") or "")
        if not strategy_id or not run_id:
            return LivePromotionAutoApplyResponse(
                world_id=world_id,
                applied=False,
                reason="missing_source_identifiers",
            )

        plan_resp = await get_live_promotion_plan(world_id, strategy_id=strategy_id, run_id=run_id)
        if "validation_failed" in plan_resp.blocked_reasons:
            return LivePromotionAutoApplyResponse(
                world_id=world_id,
                applied=False,
                reason="validation_failed",
                source_strategy_id=strategy_id,
                source_run_id=run_id,
                plan=plan_resp.plan,
            )
        if "risk_snapshot_missing_or_expired" in plan_resp.blocked_reasons:
            return LivePromotionAutoApplyResponse(
                world_id=world_id,
                applied=False,
                reason="risk_snapshot_missing_or_expired",
                source_strategy_id=strategy_id,
                source_run_id=run_id,
                plan=plan_resp.plan,
            )
        max_live_slots = plan_resp.max_live_slots
        if max_live_slots is not None and len(plan_resp.target_active) > max_live_slots:
            return LivePromotionAutoApplyResponse(
                world_id=world_id,
                applied=False,
                reason="max_live_slots_exceeded",
                source_strategy_id=strategy_id,
                source_run_id=run_id,
                plan=plan_resp.plan,
            )

        cooldown_remaining = plan_resp.cooldown_remaining_sec or 0
        if cooldown_remaining > 0:
            return LivePromotionAutoApplyResponse(
                world_id=world_id,
                applied=False,
                reason="cooldown_active",
                cooldown_remaining_sec=cooldown_remaining,
                source_strategy_id=strategy_id,
                source_run_id=run_id,
                plan=plan_resp.plan,
            )

        if not _canary_allows(
            canary_fraction=plan_resp.canary_fraction,
            world_id=world_id,
            strategy_id=strategy_id,
            run_id=run_id,
        ):
            return LivePromotionAutoApplyResponse(
                world_id=world_id,
                applied=False,
                reason="canary_skipped",
                source_strategy_id=strategy_id,
                source_run_id=run_id,
                plan=plan_resp.plan,
            )

        apply_run_id = f"auto-live-{run_id}-{_utc_now_iso().replace(':', '').replace('-', '')}"
        apply_payload = ApplyRequest(
            run_id=apply_run_id,
            plan=plan_resp.plan,
        )
        await service.apply(world_id, apply_payload, gating=None)
        return LivePromotionAutoApplyResponse(
            world_id=world_id,
            applied=True,
            reason="applied",
            source_strategy_id=strategy_id,
            source_run_id=run_id,
            apply_run_id=apply_run_id,
            plan=plan_resp.plan,
        )

    @router.get(
        "/worlds/{world_id}/promotions/live/candidates",
        response_model=LivePromotionCandidatesResponse,
    )
    async def get_live_promotion_candidates(
        world_id: str,
        *,
        limit: int = 20,
        include_plan: bool = False,
    ) -> LivePromotionCandidatesResponse:
        governance = await _get_live_promotion_governance(service, world_id)
        mode_normalized = str(governance.mode or "").lower()
        if mode_normalized == "disabled":
            return LivePromotionCandidatesResponse(world_id=world_id, promotion_mode=governance.mode, candidates=[])

        runs = await service.store.list_evaluation_runs(world_id=world_id)
        paper_runs = [
            r
            for r in runs
            if isinstance(r, dict) and str(r.get("stage") or "").lower() == "paper"
        ]
        if not paper_runs:
            return LivePromotionCandidatesResponse(world_id=world_id, promotion_mode=governance.mode, candidates=[])

        def _rank(run: dict) -> tuple[datetime, datetime]:
            created = _parse_iso(str(run.get("created_at") or ""))
            updated = _parse_iso(str(run.get("updated_at") or "")) or created
            return updated, created

        by_strategy: dict[str, dict] = {}
        for run in paper_runs:
            strategy_id = str(run.get("strategy_id") or "")
            if not strategy_id:
                continue
            existing = by_strategy.get(strategy_id)
            if existing is None or _rank(run) > _rank(existing):
                by_strategy[strategy_id] = run

        selected = sorted(by_strategy.values(), key=_rank, reverse=True)
        if limit > 0:
            selected = selected[: int(limit)]

        current_active = await service.store.get_decisions(world_id)
        current_set = {str(v) for v in current_active if str(v).strip()}

        candidates: list[LivePromotionCandidate] = []
        for run in selected:
            summary = run.get("summary") if isinstance(run, dict) else None
            if not isinstance(summary, dict):
                continue
            status = str(summary.get("status") or "").lower()
            if status not in {"pass", "warn"}:
                continue
            active_set = summary.get("active_set")
            if not isinstance(active_set, list) or not all(isinstance(v, str) for v in active_set):
                continue
            target_set = {str(v) for v in active_set if str(v).strip()}
            if not target_set:
                continue
            target_active = sorted(target_set)
            override_status = str(summary.get("override_status") or "none").lower()
            block_reasons = await _compute_promotion_block_reasons(
                service,
                world_id,
                run,
                governance=governance,
                override_status=override_status,
                target_active=target_active,
            )
            pending_manual_approval = block_reasons == ["manual_approval_required"]
            eligible = block_reasons in ([], ["manual_approval_required"])
            plan = None
            if include_plan:
                plan = ApplyPlan(
                    activate=sorted(target_set - current_set),
                    deactivate=sorted(current_set - target_set),
                )
            candidates.append(
                LivePromotionCandidate(
                    strategy_id=str(run.get("strategy_id") or ""),
                    run_id=str(run.get("run_id") or ""),
                    created_at=str(run.get("created_at") or "") or None,
                    updated_at=str(run.get("updated_at") or "") or None,
                    status=status or None,
                    override_status=override_status,
                    pending_manual_approval=pending_manual_approval,
                    eligible=eligible,
                    blocked_reasons=block_reasons,
                    target_active=target_active,
                    plan=plan,
                )
            )

        return LivePromotionCandidatesResponse(
            world_id=world_id,
            promotion_mode=governance.mode,
            candidates=candidates,
        )

    return router
