from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..schemas import EvaluationRunModel
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

    return router
