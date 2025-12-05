from __future__ import annotations

from datetime import datetime, timedelta, timezone
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
    DEFAULT_TTL_SECONDS = 300

    def _compute_staleness(updated_at: str | None) -> tuple[str, bool]:
        ttl = f"{DEFAULT_TTL_SECONDS}s"
        if not updated_at:
            return ttl, False
        try:
            parsed = datetime.fromisoformat(updated_at)
        except ValueError:
            return ttl, False
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - parsed
        return ttl, delta > timedelta(seconds=DEFAULT_TTL_SECONDS)

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
        if world_id and not states:
            raise HTTPException(status_code=404, detail="allocation snapshot not found")
        allocations: Dict[str, WorldAllocationSnapshot] = {}
        for wid, state in states.items():
            ttl, stale = _compute_staleness(state.updated_at)
            payload = {**state.to_dict(), "ttl": ttl, "stale": stale}
            allocations[wid] = WorldAllocationSnapshot(**payload)
        return AllocationSnapshotResponse(allocations=allocations)

    return router


__all__ = ["create_allocations_router"]
