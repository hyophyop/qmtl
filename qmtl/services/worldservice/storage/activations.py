"""Repository tracking world activation state."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Mapping

from .auditable import AuditableRepository, AuditSink
from .models import ActivationEntry, ActivationState, WorldActivation


class ActivationRepository(AuditableRepository):
    """Tracks activation state per world."""

    def __init__(self, audit: AuditSink) -> None:
        super().__init__(audit)
        self.activations: Dict[str, ActivationState] = {}

    def get(self, world_id: str, strategy_id: str | None = None, side: str | None = None) -> Dict[str, Any]:
        record = self.activations.get(world_id)
        if not record:
            return {"version": 0, "state": {}}
        if strategy_id is not None and side is not None:
            entry = record.state.get(strategy_id, {}).get(side)
            payload: Dict[str, Any] = {"version": record.version}
            if entry:
                payload.update(entry.to_dict())
            return payload
        snapshot = WorldActivation.from_internal(record)
        return {"version": snapshot.version, "state": snapshot.state}

    def snapshot(self, world_id: str) -> WorldActivation:
        record = self.activations.get(world_id)
        if not record:
            return WorldActivation()
        return WorldActivation.from_internal(record.clone())

    def restore(self, world_id: str, snapshot: WorldActivation) -> None:
        self.activations[world_id] = snapshot.to_internal()

    def update(self, world_id: str, payload: Mapping[str, Any]) -> tuple[int, Dict[str, Any]]:
        record = self.activations.setdefault(world_id, ActivationState())
        record.version += 1
        strategy_id = str(payload["strategy_id"])
        side = str(payload["side"])
        ts = payload.get("ts") or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        etag = f"act:{world_id}:{strategy_id}:{side}:{record.version}"
        entry = ActivationEntry(
            active=bool(payload.get("active", False)),
            weight=float(payload.get("weight", 1.0)),
            freeze=bool(payload.get("freeze", False)),
            drain=bool(payload.get("drain", False)),
            effective_mode=payload.get("effective_mode"),
            run_id=payload.get("run_id"),
            ts=ts,
            etag=etag,
        )
        record.state.setdefault(strategy_id, {})[side] = entry
        audit_payload = {"event": "activation_updated", "version": record.version, "strategy_id": strategy_id, "side": side}
        audit_payload.update(entry.to_dict())
        self._emit_audit(world_id, audit_payload)
        return record.version, entry.to_dict()

    def clear(self, world_id: str) -> None:
        self.activations.pop(world_id, None)


__all__ = ["ActivationRepository"]
