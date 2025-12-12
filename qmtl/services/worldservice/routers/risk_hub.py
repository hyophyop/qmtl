from __future__ import annotations

from typing import Any, Dict, Callable, Awaitable

import inspect
import logging
from fastapi import Request

from fastapi import APIRouter, HTTPException

from ..risk_hub import PortfolioSnapshot, RiskSignalHub
from ..controlbus_producer import ControlBusProducer

logger = logging.getLogger(__name__)


def create_risk_hub_router(
    hub: RiskSignalHub,
    *,
    bus: ControlBusProducer | None = None,
    schedule_extended_validation: Callable[[str], Awaitable[Any]] | Callable[[str], Any] | None = None,
    expected_token: str | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/risk-hub", tags=["risk-hub"])

    @router.post("/worlds/{world_id}/snapshots")
    async def upsert_snapshot(world_id: str, payload: Dict[str, Any], request: Request) -> Dict[str, Any]:
        if expected_token:
            auth = request.headers.get("Authorization") or ""
            if not auth.startswith("Bearer ") or auth.split(" ", 1)[1] != expected_token:
                raise HTTPException(status_code=401, detail="unauthorized")
        actor = request.headers.get("X-Actor")
        if not actor:
            raise HTTPException(status_code=400, detail="missing actor header")
        stage = request.headers.get("X-Stage")
        if payload.get("world_id") and payload["world_id"] != world_id:
            raise HTTPException(status_code=400, detail="world_id mismatch")
        try:
            snapshot = PortfolioSnapshot.from_payload({"world_id": world_id, **payload})
            # basic validation + weight normalization check occurs in hub
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"invalid snapshot: {exc}") from exc
        snapshot.provenance.setdefault("actor", actor)
        if stage:
            snapshot.provenance.setdefault("stage", stage)
        await hub.upsert_snapshot(snapshot)
        if bus is not None:
            try:
                await bus.publish_risk_snapshot_updated(world_id, snapshot.to_dict())
            except Exception:  # pragma: no cover - best-effort
                logger.exception("Failed to publish risk snapshot to ControlBus")
        if schedule_extended_validation is not None:
            try:
                maybe = schedule_extended_validation(world_id)
                if inspect.isawaitable(maybe):
                    await maybe
            except Exception:  # pragma: no cover - best-effort
                logger.exception("Failed to schedule extended validation from risk hub update")
        return snapshot.to_dict()

    @router.get("/worlds/{world_id}/snapshots/latest")
    async def get_latest_snapshot(world_id: str) -> Dict[str, Any]:
        snap = await hub.latest_snapshot(world_id)
        if snap is None:
            raise HTTPException(status_code=404, detail="snapshot not found")
        return snap.to_dict()

    @router.get("/worlds/{world_id}/snapshots")
    async def list_snapshots(world_id: str, limit: int = 10) -> Dict[str, Any]:
        snapshots = await hub.list_snapshots(world_id, limit=limit)
        return {"snapshots": snapshots}

    return router


__all__ = ["create_risk_hub_router"]
