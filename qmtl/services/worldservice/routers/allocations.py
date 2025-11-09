from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..schemas import AllocationUpsertRequest, AllocationUpsertResponse
from ..services import WorldService


def create_allocations_router(service: WorldService) -> APIRouter:
    router = APIRouter()

    @router.post("/allocations", response_model=AllocationUpsertResponse)
    async def post_allocations(payload: AllocationUpsertRequest) -> AllocationUpsertResponse:
        try:
            return await service.upsert_allocations(payload)
        except ValueError as exc:  # pragma: no cover - defensive guard
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return router


__all__ = ["create_allocations_router"]
