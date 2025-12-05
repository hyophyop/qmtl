from __future__ import annotations

from typing import Dict

from fastapi import APIRouter, HTTPException

from ..schemas import (
    AllocationSnapshotResponse,
    AllocationUpsertRequest,
    AllocationUpsertResponse,
    WorldAllocationSnapshot,
)
from ..services import WorldService


def create_allocations_router(service: WorldService) -> APIRouter:
    router = APIRouter()

    @router.post("/allocations", response_model=AllocationUpsertResponse)
    async def post_allocations(payload: AllocationUpsertRequest) -> AllocationUpsertResponse:
        try:
            return await service.upsert_allocations(payload)
        except ValueError as exc:  # pragma: no cover - defensive guard
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/allocations", response_model=AllocationSnapshotResponse)
    async def get_allocations(world_id: str | None = None) -> AllocationSnapshotResponse:
        states = (
            await service.store.get_world_allocation_states([world_id])
            if world_id
            else await service.store.get_world_allocation_states()
        )
        allocations: Dict[str, WorldAllocationSnapshot] = {
            wid: WorldAllocationSnapshot(**state.to_dict()) for wid, state in states.items()
        }
        return AllocationSnapshotResponse(allocations=allocations)

    return router


__all__ = ["create_allocations_router"]
