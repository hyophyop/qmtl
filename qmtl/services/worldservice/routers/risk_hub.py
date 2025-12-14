from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Dict, Callable, Awaitable

import inspect
import logging
from fastapi import Request

from fastapi import APIRouter, HTTPException

from qmtl.services.risk_hub_contract import normalize_and_validate_snapshot

from .. import metrics as ws_metrics
from ..risk_hub import PortfolioSnapshot, RiskSignalHub, RiskSnapshotConflictError
from ..controlbus_producer import ControlBusProducer

logger = logging.getLogger(__name__)


def create_risk_hub_router(
    hub: RiskSignalHub,
    *,
    bus: ControlBusProducer | None = None,
    schedule_extended_validation: Callable[[str], Awaitable[Any]] | Callable[[str], Any] | None = None,
    expected_token: str | None = None,
    ttl_sec_default: int = 900,
    ttl_sec_max: int = 86400,
    allowed_actors: Sequence[str] | None = None,
    allowed_stages: Sequence[str] | None = None,
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
        if not stage:
            raise HTTPException(status_code=400, detail="missing stage header")
        if payload.get("world_id") and payload["world_id"] != world_id:
            raise HTTPException(status_code=400, detail="world_id mismatch")
        try:
            validated = normalize_and_validate_snapshot(
                world_id,
                payload,
                actor=actor,
                stage=stage,
                ttl_sec_default=ttl_sec_default,
                ttl_sec_max=ttl_sec_max,
                allowed_actors=allowed_actors,
                allowed_stages=allowed_stages,
            )
            snapshot = PortfolioSnapshot.from_payload(validated)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:  # pragma: no cover - defensive mapping
            raise HTTPException(status_code=422, detail=f"invalid snapshot: {exc}") from exc
        stage_label = str((snapshot.provenance or {}).get("stage") or stage or "unknown")
        try:
            deduped = await hub.upsert_snapshot(snapshot)
        except RiskSnapshotConflictError as exc:
            ws_metrics.record_risk_snapshot_failed(world_id, stage=stage_label)
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            detail = str(exc)
            if "expired" in detail.lower():
                ws_metrics.record_risk_snapshot_expired(world_id, stage=stage_label)
            else:
                ws_metrics.record_risk_snapshot_failed(world_id, stage=stage_label)
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if deduped:
            ws_metrics.record_risk_snapshot_dedupe(world_id, stage=stage_label)
        else:
            ws_metrics.record_risk_snapshot_processed(world_id, stage=stage_label)
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

    @router.get("/worlds/{world_id}/snapshots/lookup")
    async def lookup_snapshot(
        world_id: str,
        version: str | None = None,
        as_of: str | None = None,
    ) -> Dict[str, Any]:
        snap = await hub.get_snapshot(world_id, version=version, as_of=as_of)
        if snap is None:
            raise HTTPException(status_code=404, detail="snapshot not found")
        return snap.to_dict()

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
