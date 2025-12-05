from __future__ import annotations

from typing import Dict

from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, HTTPException

from .. import metrics as ws_metrics
from ..schemas import (
    AllocationSnapshotResponse,
    AllocationUpsertRequest,
    AllocationUpsertResponse,
    WorldAllocationSnapshot,
)
from ..services import WorldService


_STALE_THRESHOLD = timedelta(minutes=5)


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
        now = datetime.now(timezone.utc)
        states = (
            await service.store.get_world_allocation_states([world_id])
            if world_id
            else await service.store.get_world_allocation_states()
        )
        allocations: Dict[str, WorldAllocationSnapshot] = {}
        for wid, state in states.items():
            stale = _is_stale(state.updated_at, now)
            state.stale = stale
            ws_metrics.record_allocation_snapshot(wid, stale=stale)
            allocations[wid] = WorldAllocationSnapshot(**state.to_dict())
        return AllocationSnapshotResponse(allocations=allocations)

    return router


__all__ = ["create_allocations_router"]


def _is_stale(updated_at: str | None, now: datetime) -> bool:
    if not updated_at:
        return True
    try:
        ts = datetime.fromisoformat(updated_at)
    except ValueError:
        return True
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return (now - ts) > _STALE_THRESHOLD
