from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Any, Mapping

from fastapi import APIRouter, HTTPException

from ..policy_engine import Policy
from ..schemas import (
    CampaignStatusResponse,
    CampaignStrategyStatus,
    CampaignTickAction,
    CampaignTickResponse,
    CampaignWindowStatus,
)
from ..services import WorldService


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_iso(ts: str | None) -> datetime:
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


@dataclass(frozen=True, slots=True)
class CampaignPolicy:
    backtest_window: str | None
    paper_window: str | None
    min_sample_days: int | None
    min_trades_total: int | None


def _extract_campaign_policy(policy: object) -> CampaignPolicy:
    if isinstance(policy, Policy):
        campaign = policy.campaign
        backtest_window = campaign.backtest.window if campaign and campaign.backtest else None
        paper_window = campaign.paper.window if campaign and campaign.paper else None
        common = campaign.common if campaign else None
        min_sample_days = common.min_sample_days if common else None
        min_trades_total = common.min_trades_total if common else None
        return CampaignPolicy(
            backtest_window=backtest_window,
            paper_window=paper_window,
            min_sample_days=min_sample_days,
            min_trades_total=min_trades_total,
        )
    if isinstance(policy, dict):
        campaign = policy.get("campaign")
        if not isinstance(campaign, dict):
            return CampaignPolicy(None, None, None, None)
        backtest = campaign.get("backtest") if isinstance(campaign.get("backtest"), dict) else {}
        paper = campaign.get("paper") if isinstance(campaign.get("paper"), dict) else {}
        common = campaign.get("common") if isinstance(campaign.get("common"), dict) else {}
        backtest_window = backtest.get("window")
        paper_window = paper.get("window")
        min_sample_days = common.get("min_sample_days")
        min_trades_total = common.get("min_trades_total")
        try:
            min_sample_days = int(min_sample_days) if min_sample_days is not None else None
        except Exception:
            min_sample_days = None
        try:
            min_trades_total = int(min_trades_total) if min_trades_total is not None else None
        except Exception:
            min_trades_total = None
        return CampaignPolicy(
            backtest_window=str(backtest_window) if backtest_window is not None else None,
            paper_window=str(paper_window) if paper_window is not None else None,
            min_sample_days=min_sample_days,
            min_trades_total=min_trades_total,
        )
    return CampaignPolicy(None, None, None, None)


def _metric_float(metrics: Mapping[str, Any] | None, section: str, key: str) -> float | None:
    if not metrics:
        return None
    direct = metrics.get(key)
    if isinstance(direct, (int, float)) and not isinstance(direct, bool):
        return float(direct)
    block = metrics.get(section)
    if isinstance(block, Mapping):
        value = block.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
    return None


def _metric_int(metrics: Mapping[str, Any] | None, section: str, key: str) -> int | None:
    if not metrics:
        return None
    direct = metrics.get(key)
    if isinstance(direct, int) and not isinstance(direct, bool):
        return int(direct)
    block = metrics.get(section)
    if isinstance(block, Mapping):
        value = block.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            return int(value)
    return None


def _estimate_sample_days(metrics: Mapping[str, Any] | None) -> int | None:
    years = _metric_float(metrics, "sample", "effective_history_years")
    if years is None:
        return None
    return max(0, int(years * 365))


def _latest_run_by_stage(runs: list[dict], stage: str) -> dict | None:
    stage_runs = [r for r in runs if str(r.get("stage") or "").lower() == stage]
    if not stage_runs:
        return None
    return max(stage_runs, key=lambda r: (_parse_iso(str(r.get("updated_at") or "")), _parse_iso(str(r.get("created_at") or ""))))


def _window_observation(runs: list[dict], stage: str) -> tuple[datetime | None, datetime | None, int | None]:
    stage_runs = [r for r in runs if str(r.get("stage") or "").lower() == stage]
    if not stage_runs:
        return None, None, None
    starts = [_parse_iso(str(r.get("created_at") or "")) for r in stage_runs]
    ends = [_parse_iso(str(r.get("updated_at") or "")) for r in stage_runs]
    start = min(starts) if starts else None
    end = max(ends) if ends else None
    if start is None or end is None or start == datetime.min.replace(tzinfo=timezone.utc) or end == datetime.min.replace(tzinfo=timezone.utc):
        return None, None, None
    observed_sec = max(0, int((end - start).total_seconds()))
    return start, end, observed_sec


def _window_status(window: str | None, *, start: datetime | None, end: datetime | None, observed_sec: int | None) -> CampaignWindowStatus:
    required_sec = _parse_duration_seconds(window)
    progress = None
    satisfied = False
    if required_sec is not None:
        if observed_sec is None:
            progress = 0.0
        elif required_sec <= 0:
            progress = 1.0
            satisfied = True
        else:
            progress = min(1.0, max(0.0, observed_sec / required_sec))
            satisfied = progress >= 1.0
    return CampaignWindowStatus(
        window=window,
        required_sec=required_sec,
        observed_sec=observed_sec,
        progress=progress,
        started_at=start.isoformat().replace("+00:00", "Z") if start else None,
        ended_at=end.isoformat().replace("+00:00", "Z") if end else None,
        satisfied=satisfied,
    )


def create_campaigns_router(service: WorldService) -> APIRouter:
    router = APIRouter()

    @router.get(
        "/worlds/{world_id}/campaign/status",
        response_model=CampaignStatusResponse,
    )
    async def get_campaign_status(
        world_id: str,
        *,
        strategy_id: str | None = None,
    ) -> CampaignStatusResponse:
        policy_obj = await service.store.get_default_policy(world_id)
        campaign_policy = _extract_campaign_policy(policy_obj)
        try:
            _ = _parse_duration_seconds(campaign_policy.backtest_window)
            _ = _parse_duration_seconds(campaign_policy.paper_window)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        runs = await service.store.list_evaluation_runs(world_id=world_id, strategy_id=strategy_id)
        grouped: dict[str, list[dict]] = {}
        for run in runs:
            if not isinstance(run, dict):
                continue
            sid = str(run.get("strategy_id") or "")
            if not sid:
                continue
            grouped.setdefault(sid, []).append(run)

        statuses: list[CampaignStrategyStatus] = []
        for sid, sruns in grouped.items():
            backtest_latest = _latest_run_by_stage(sruns, "backtest")
            paper_latest = _latest_run_by_stage(sruns, "paper")
            live_latest = _latest_run_by_stage(sruns, "live")

            if live_latest is not None:
                phase = "live_campaign"
            elif paper_latest is not None:
                phase = "paper_campaign"
            else:
                phase = "backtest_campaign"

            reasons: list[str] = []

            backtest_start, backtest_end, backtest_observed = _window_observation(sruns, "backtest")
            paper_start, paper_end, paper_observed = _window_observation(sruns, "paper")

            backtest_window = _window_status(
                campaign_policy.backtest_window,
                start=backtest_start,
                end=backtest_end,
                observed_sec=backtest_observed,
            )
            paper_window = _window_status(
                campaign_policy.paper_window,
                start=paper_start,
                end=paper_end,
                observed_sec=paper_observed,
            )

            latest_metrics: Mapping[str, Any] | None = None
            latest_summary: Mapping[str, Any] | None = None
            if paper_latest is not None:
                latest_metrics = paper_latest.get("metrics") if isinstance(paper_latest.get("metrics"), Mapping) else None
                latest_summary = paper_latest.get("summary") if isinstance(paper_latest.get("summary"), Mapping) else None
            elif backtest_latest is not None:
                latest_metrics = backtest_latest.get("metrics") if isinstance(backtest_latest.get("metrics"), Mapping) else None
                latest_summary = backtest_latest.get("summary") if isinstance(backtest_latest.get("summary"), Mapping) else None

            sample_days = _estimate_sample_days(latest_metrics)
            trades_total = _metric_int(latest_metrics, "sample", "n_trades_total")
            sharpe = _metric_float(latest_metrics, "returns", "sharpe")
            max_drawdown = _metric_float(latest_metrics, "returns", "max_drawdown")

            if campaign_policy.min_sample_days is not None:
                if sample_days is None:
                    reasons.append("missing_sample_days_metric")
                elif sample_days < campaign_policy.min_sample_days:
                    reasons.append("insufficient_sample_days")

            if campaign_policy.min_trades_total is not None:
                if trades_total is None:
                    reasons.append("missing_trades_metric")
                elif trades_total < campaign_policy.min_trades_total:
                    reasons.append("insufficient_trades")

            backtest_ok = backtest_window.satisfied or campaign_policy.backtest_window is None
            paper_ok = paper_window.satisfied or campaign_policy.paper_window is None

            backtest_status = (
                str((backtest_latest or {}).get("summary", {}).get("status") or "").lower()
                if backtest_latest
                else ""
            )
            paper_status = (
                str((paper_latest or {}).get("summary", {}).get("status") or "").lower()
                if paper_latest
                else ""
            )
            if backtest_latest is None:
                reasons.append("missing_backtest_run")
            if paper_latest is None:
                reasons.append("missing_paper_run")
            if not backtest_ok:
                reasons.append("backtest_window_incomplete")
            if not paper_ok:
                reasons.append("paper_window_incomplete")

            promotable_to_paper = (
                backtest_latest is not None
                and backtest_ok
                and backtest_status in {"pass", "warn"}
                and "insufficient_sample_days" not in reasons
                and "insufficient_trades" not in reasons
                and "missing_sample_days_metric" not in reasons
                and "missing_trades_metric" not in reasons
            )
            promotable_to_live = (
                paper_latest is not None
                and paper_ok
                and paper_status in {"pass", "warn"}
                and "insufficient_sample_days" not in reasons
                and "insufficient_trades" not in reasons
                and "missing_sample_days_metric" not in reasons
                and "missing_trades_metric" not in reasons
            )

            statuses.append(
                CampaignStrategyStatus(
                    strategy_id=sid,
                    phase=phase,
                    latest_backtest_run_id=str((backtest_latest or {}).get("run_id") or "") or None,
                    latest_paper_run_id=str((paper_latest or {}).get("run_id") or "") or None,
                    latest_live_run_id=str((live_latest or {}).get("run_id") or "") or None,
                    backtest=backtest_window,
                    paper=paper_window,
                    sample_days=sample_days,
                    trades_total=trades_total,
                    sharpe=sharpe,
                    max_drawdown=max_drawdown,
                    promotable_to_paper=promotable_to_paper,
                    promotable_to_live=promotable_to_live,
                    reasons=reasons,
                )
            )

        statuses.sort(key=lambda s: s.strategy_id)
        config = {
            "backtest_window": campaign_policy.backtest_window,
            "paper_window": campaign_policy.paper_window,
            "min_sample_days": campaign_policy.min_sample_days,
            "min_trades_total": campaign_policy.min_trades_total,
        }
        return CampaignStatusResponse(
            world_id=world_id,
            generated_at=_utc_now_iso(),
            config=config,
            strategies=statuses,
        )

    @router.post(
        "/worlds/{world_id}/campaign/tick",
        response_model=CampaignTickResponse,
    )
    async def post_campaign_tick(
        world_id: str,
        *,
        strategy_id: str | None = None,
    ) -> CampaignTickResponse:
        """Emit recommended external-scheduler actions for Phase 4 campaigns.

        This endpoint is intentionally side-effect free: it does not call /evaluate
        nor /apply. It only computes a suggested next step based on recorded runs.
        """

        status = await get_campaign_status(world_id, strategy_id=strategy_id)

        policy_obj = await service.store.get_default_policy(world_id)
        governance_mode: str | None = None
        if isinstance(policy_obj, Policy):
            governance_mode = (
                str(policy_obj.governance.live_promotion.mode)
                if policy_obj.governance and policy_obj.governance.live_promotion
                else None
            )
        elif isinstance(policy_obj, dict):
            gov = policy_obj.get("governance") if isinstance(policy_obj.get("governance"), dict) else {}
            lp = gov.get("live_promotion") if isinstance(gov.get("live_promotion"), dict) else {}
            mode = lp.get("mode")
            governance_mode = str(mode) if mode is not None else None

        actions: list[CampaignTickAction] = []
        for strat in status.strategies:
            sid = strat.strategy_id
            if strat.phase == "backtest_campaign":
                if strat.promotable_to_paper:
                    actions.append(
                        CampaignTickAction(
                            action="evaluate",
                            strategy_id=sid,
                            stage="paper",
                            reason="promotable_to_paper",
                            suggested_method="POST",
                            suggested_endpoint=f"/worlds/{world_id}/evaluate",
                            suggested_body={
                                "strategy_id": sid,
                                "stage": "paper",
                                "risk_tier": "low",
                                "metrics": {"<strategy_id>": {"returns": {"sharpe": 0.0}}},
                            },
                        )
                    )
                else:
                    actions.append(
                        CampaignTickAction(
                            action="evaluate",
                            strategy_id=sid,
                            stage="backtest",
                            reason="continue_backtest_campaign",
                            suggested_method="POST",
                            suggested_endpoint=f"/worlds/{world_id}/evaluate",
                            suggested_body={
                                "strategy_id": sid,
                                "stage": "backtest",
                                "risk_tier": "low",
                                "metrics": {"<strategy_id>": {"returns": {"sharpe": 0.0}}},
                            },
                        )
                    )
                continue

            if strat.phase == "paper_campaign":
                if strat.promotable_to_live:
                    if str(governance_mode or "").lower() == "auto_apply":
                        actions.append(
                            CampaignTickAction(
                                action="auto_apply_live",
                                reason="promotable_to_live",
                                suggested_method="POST",
                                suggested_endpoint=f"/worlds/{world_id}/promotions/live/auto-apply",
                            )
                        )
                    else:
                        run_id = strat.latest_paper_run_id or ""
                        if not run_id:
                            run_id = "latest"
                        actions.append(
                            CampaignTickAction(
                                action="manual_approval_required",
                                strategy_id=sid,
                                reason="promotable_to_live",
                                suggested_method="GET",
                                suggested_endpoint=f"/worlds/{world_id}/promotions/live/plan",
                                suggested_params={"strategy_id": sid, "run_id": run_id},
                            )
                        )
                else:
                    actions.append(
                        CampaignTickAction(
                            action="evaluate",
                            strategy_id=sid,
                            stage="paper",
                            reason="continue_paper_campaign",
                            suggested_method="POST",
                            suggested_endpoint=f"/worlds/{world_id}/evaluate",
                            suggested_body={
                                "strategy_id": sid,
                                "stage": "paper",
                                "risk_tier": "low",
                                "metrics": {"<strategy_id>": {"returns": {"sharpe": 0.0}}},
                            },
                        )
                    )
                continue

            actions.append(
                CampaignTickAction(
                    action="observe_live",
                    strategy_id=sid,
                    reason="already_in_live_campaign",
                )
            )

        return CampaignTickResponse(world_id=world_id, generated_at=_utc_now_iso(), actions=actions)

    return router


__all__ = ["create_campaigns_router"]
