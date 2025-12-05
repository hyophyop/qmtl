from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict

from fastapi import APIRouter, HTTPException

from .. import metrics as ws_metrics
from ..schemas import (
    AllocationSnapshotResponse,
    AllocationUpsertRequest,
    AllocationUpsertResponse,
    WorldAllocationSnapshot,
)
from ..services import WorldService


_DEFAULT_TTL_SECONDS = 300
_STALE_THRESHOLD = timedelta(seconds=_DEFAULT_TTL_SECONDS)


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
        if world_id and not states:
            raise HTTPException(status_code=404, detail="allocation snapshot not found")
        allocations: Dict[str, WorldAllocationSnapshot] = {}
        for wid, state in states.items():
            ttl, stale = _compute_ttl_and_staleness(state.updated_at, now)
            ws_metrics.record_allocation_snapshot(wid, stale=stale)
            payload = {**state.to_dict(), "ttl": ttl, "stale": stale}
            allocations[wid] = WorldAllocationSnapshot(**payload)
        return AllocationSnapshotResponse(allocations=allocations)

    return router


__all__ = ["create_allocations_router"]


def _compute_ttl_and_staleness(updated_at: str | None, now: datetime) -> tuple[str, bool]:
    ttl = f"{_DEFAULT_TTL_SECONDS}s"
    if not updated_at:
        return ttl, True
    try:
        normalized_updated_at = (
            f"{updated_at[:-1]}+00:00" if updated_at.endswith("Z") else updated_at
        )
        parsed = datetime.fromisoformat(normalized_updated_at)
    except ValueError:
        return ttl, True
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return ttl, (now - parsed) > _STALE_THRESHOLD
