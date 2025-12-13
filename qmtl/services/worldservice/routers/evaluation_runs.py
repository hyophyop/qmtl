from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..schemas import ExPostFailureRecord, EvaluationOverride, EvaluationRunHistoryItem, EvaluationRunModel
from ..services import WorldService


def create_evaluation_runs_router(service: WorldService) -> APIRouter:
    router = APIRouter()

    @router.get(
        "/worlds/{world_id}/strategies/{strategy_id}/runs",
        response_model=list[EvaluationRunModel],
    )
    async def list_evaluation_runs(world_id: str, strategy_id: str) -> list[EvaluationRunModel]:
        runs = await service.store.list_evaluation_runs(world_id=world_id, strategy_id=strategy_id)
        return [EvaluationRunModel(**run) for run in runs]

    @router.get(
        "/worlds/{world_id}/strategies/{strategy_id}/runs/{run_id}",
        response_model=EvaluationRunModel,
    )
    async def get_evaluation_run(world_id: str, strategy_id: str, run_id: str) -> EvaluationRunModel:
        record = await service.store.get_evaluation_run(world_id, strategy_id, run_id)
        if record is None:
            raise HTTPException(status_code=404, detail="evaluation run not found")
        return EvaluationRunModel(**record)

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
