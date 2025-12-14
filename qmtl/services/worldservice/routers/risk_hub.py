from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
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

def _parse_iso_ts(value: Any) -> float:
    text = str(value or "").strip()
    if not text:
        return 0.0
    candidate = text
    if candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"
    try:
        return float(datetime.fromisoformat(candidate).timestamp())
    except Exception:
        return 0.0


async def _expand_snapshot_payload(
    hub: RiskSignalHub,
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    covariance_ref = payload.get("covariance_ref")
    if payload.get("covariance") is None and isinstance(covariance_ref, str) and covariance_ref:
        cov = await hub.resolve_blob_ref(covariance_ref)
        if isinstance(cov, Mapping):
            payload["covariance"] = dict(cov)

    realized_ref = payload.get("realized_returns_ref")
    if payload.get("realized_returns") is None and isinstance(realized_ref, str) and realized_ref:
        realized = await hub.resolve_blob_ref(realized_ref)
        if realized is not None:
            payload["realized_returns"] = realized

    stress_ref = payload.get("stress_ref")
    if payload.get("stress") is None and isinstance(stress_ref, str) and stress_ref:
        stress = await hub.resolve_blob_ref(stress_ref)
        if isinstance(stress, Mapping):
            payload["stress"] = dict(stress)

    return payload


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
        expand: bool = False,
    ) -> Dict[str, Any]:
        snap = await hub.get_snapshot(world_id, version=version, as_of=as_of)
        if snap is None:
            raise HTTPException(status_code=404, detail="snapshot not found")
        payload = snap.to_dict()
        if expand:
            payload = await _expand_snapshot_payload(hub, payload)
        return payload

    @router.get("/worlds/{world_id}/snapshots/latest")
    async def get_latest_snapshot(
        world_id: str,
        stage: str | None = None,
        actor: str | None = None,
        *,
        limit: int = 50,
        expand: bool = False,
    ) -> Dict[str, Any]:
        normalized_stage = str(stage or "").strip().lower() or None
        normalized_actor = str(actor or "").strip() or None

        payload: Dict[str, Any] | None = None
        if normalized_stage is None and normalized_actor is None:
            snap = await hub.latest_snapshot(world_id)
            if snap is None:
                raise HTTPException(status_code=404, detail="snapshot not found")
            payload = snap.to_dict()
        else:
            status = await hub.list_snapshots(world_id, limit=max(1, int(limit or 0)))
            candidates: list[dict[str, Any]] = []
            for item in status:
                if not isinstance(item, dict):
                    continue
                prov = item.get("provenance")
                prov_map = prov if isinstance(prov, Mapping) else {}
                item_stage = str(prov_map.get("stage") or "").strip().lower()
                item_actor = str(prov_map.get("actor") or "").strip()
                if normalized_stage is not None and item_stage != normalized_stage:
                    continue
                if normalized_actor is not None and item_actor != normalized_actor:
                    continue
                candidates.append(item)
            if not candidates:
                raise HTTPException(status_code=404, detail="snapshot not found")

            def _rank(item: dict[str, Any]) -> tuple[float, float]:
                return (_parse_iso_ts(item.get("as_of")), _parse_iso_ts(item.get("created_at")))

            payload = max(candidates, key=_rank)

        if expand and payload is not None:
            payload = await _expand_snapshot_payload(hub, payload)
        return payload or {}

    @router.get("/worlds/{world_id}/snapshots")
    async def list_snapshots(
        world_id: str,
        limit: int = 10,
        stage: str | None = None,
        actor: str | None = None,
        expand: bool = False,
    ) -> Dict[str, Any]:
        snapshots = await hub.list_snapshots(world_id, limit=limit)
        normalized_stage = str(stage or "").strip().lower() or None
        normalized_actor = str(actor or "").strip() or None
        if normalized_stage is not None or normalized_actor is not None:
            filtered: list[dict[str, Any]] = []
            for item in snapshots:
                if not isinstance(item, dict):
                    continue
                prov = item.get("provenance")
                prov_map = prov if isinstance(prov, Mapping) else {}
                item_stage = str(prov_map.get("stage") or "").strip().lower()
                item_actor = str(prov_map.get("actor") or "").strip()
                if normalized_stage is not None and item_stage != normalized_stage:
                    continue
                if normalized_actor is not None and item_actor != normalized_actor:
                    continue
                filtered.append(item)
            snapshots = filtered
        if expand:
            snapshots = [await _expand_snapshot_payload(hub, dict(item)) for item in snapshots]
        return {"snapshots": snapshots}

    return router


__all__ = ["create_risk_hub_router"]
