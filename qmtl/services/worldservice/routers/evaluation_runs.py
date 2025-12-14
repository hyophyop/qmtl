from __future__ import annotations

from typing import Any, Mapping

from fastapi import APIRouter, HTTPException

from ..schemas import (
    EvaluationRunMetricsResponse,
    ExPostFailureRecord,
    EvaluationOverride,
    EvaluationRunHistoryItem,
    EvaluationRunModel,
)
from ..services import WorldService


def _metrics_present(metrics: object) -> bool:
    if metrics is None:
        return False
    if isinstance(metrics, Mapping):
        return bool(metrics)
    return True


def _run_status(metrics: object) -> str:
    return "evaluated" if _metrics_present(metrics) else "evaluating"


def _run_links(*, world_id: str, strategy_id: str, run_id: str) -> dict[str, str]:
    return {
        "metrics": f"/worlds/{world_id}/strategies/{strategy_id}/runs/{run_id}/metrics",
        "history": f"/worlds/{world_id}/strategies/{strategy_id}/runs/{run_id}/history",
    }


def create_evaluation_runs_router(service: WorldService) -> APIRouter:
    router = APIRouter()

    @router.get(
        "/worlds/{world_id}/strategies/{strategy_id}/runs",
        response_model=list[EvaluationRunModel],
    )
    async def list_evaluation_runs(world_id: str, strategy_id: str) -> list[EvaluationRunModel]:
        runs = await service.store.list_evaluation_runs(world_id=world_id, strategy_id=strategy_id)
        enriched: list[EvaluationRunModel] = []
        for run in runs:
            if not isinstance(run, dict):
                continue
            payload: dict[str, Any] = dict(run)
            rid = str(payload.get("run_id") or "")
            payload["status"] = _run_status(payload.get("metrics"))
            if rid:
                payload["links"] = _run_links(world_id=world_id, strategy_id=strategy_id, run_id=rid)
            enriched.append(EvaluationRunModel(**payload))
        return enriched

    @router.get(
        "/worlds/{world_id}/strategies/{strategy_id}/runs/{run_id}",
        response_model=EvaluationRunModel,
    )
    async def get_evaluation_run(world_id: str, strategy_id: str, run_id: str) -> EvaluationRunModel:
        record = await service.store.get_evaluation_run(world_id, strategy_id, run_id)
        if record is None:
            raise HTTPException(status_code=404, detail="evaluation run not found")
        payload: dict[str, Any] = dict(record)
        payload["status"] = _run_status(payload.get("metrics"))
        payload["links"] = _run_links(world_id=world_id, strategy_id=strategy_id, run_id=run_id)
        return EvaluationRunModel(**payload)

    @router.get(
        "/worlds/{world_id}/strategies/{strategy_id}/runs/{run_id}/metrics",
        response_model=EvaluationRunMetricsResponse,
    )
    async def get_evaluation_run_metrics(
        world_id: str, strategy_id: str, run_id: str
    ) -> EvaluationRunMetricsResponse:
        record = await service.store.get_evaluation_run(world_id, strategy_id, run_id)
        if record is None:
            raise HTTPException(status_code=404, detail="evaluation run not found")
        run = EvaluationRunModel(**dict(record))
        metrics_present = run.metrics is not None and bool(run.metrics.model_dump(exclude_none=True))
        if not metrics_present:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "E_RUN_NOT_EVALUATED",
                    "message": "evaluation run has no metrics yet",
                },
            )
        return EvaluationRunMetricsResponse(
            world_id=run.world_id,
            strategy_id=run.strategy_id,
            run_id=run.run_id,
            status=_run_status(record.get("metrics") if isinstance(record, dict) else None),
            stage=run.stage,
            risk_tier=run.risk_tier,
            metrics=run.metrics,
            validation=run.validation,
            summary=run.summary,
            created_at=run.created_at,
            updated_at=run.updated_at,
            links=_run_links(world_id=world_id, strategy_id=strategy_id, run_id=run_id),
        )

    @router.get(
        "/worlds/{world_id}/strategies/{strategy_id}/runs/{run_id}/history",
        response_model=list[EvaluationRunHistoryItem],
    )
    async def list_evaluation_run_history(
        world_id: str, strategy_id: str, run_id: str
    ) -> list[EvaluationRunHistoryItem]:
        history = await service.store.list_evaluation_run_history(
            world_id, strategy_id, run_id
        )
        items: list[EvaluationRunHistoryItem] = []
        for entry in history:
            payload = entry.get("payload")
            if not isinstance(payload, dict):
                continue
            items.append(
                EvaluationRunHistoryItem(
                    revision=int(entry.get("revision") or 0),
                    recorded_at=str(entry.get("recorded_at") or ""),
                    payload=EvaluationRunModel(**payload),
                )
            )
        return items

    @router.post(
        "/worlds/{world_id}/strategies/{strategy_id}/runs/{run_id}/override",
        response_model=EvaluationRunModel,
    )
    async def post_evaluation_override(
        world_id: str, strategy_id: str, run_id: str, payload: EvaluationOverride
    ) -> EvaluationRunModel:
        record = await service.record_evaluation_override(world_id, strategy_id, run_id, payload)
        return EvaluationRunModel(**record)

    @router.post(
        "/worlds/{world_id}/strategies/{strategy_id}/runs/{run_id}/ex-post-failures",
        response_model=EvaluationRunModel,
    )
    async def post_ex_post_failure(
        world_id: str,
        strategy_id: str,
        run_id: str,
        payload: ExPostFailureRecord,
    ) -> EvaluationRunModel:
        record = await service.record_ex_post_failure(world_id, strategy_id, run_id, payload)
        return EvaluationRunModel(**record)

    return router
