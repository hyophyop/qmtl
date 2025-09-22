"""Repository storing edge override state."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Optional

from .auditable import AuditableRepository, AuditSink
from .constants import DEFAULT_EDGE_OVERRIDES
from .models import EdgeOverrideRecord


class EdgeOverrideRepository(AuditableRepository):
    """Stores edge override state."""

    def __init__(self, audit: AuditSink) -> None:
        super().__init__(audit)
        self.overrides: Dict[str, Dict[tuple[str, str], EdgeOverrideRecord]] = {}

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    def upsert(
        self,
        world_id: str,
        src_node_id: str,
        dst_node_id: str,
        *,
        active: bool,
        reason: str | None | object,
    ) -> EdgeOverrideRecord:
        bucket = self.overrides.setdefault(world_id, {})
        key = (src_node_id, dst_node_id)
        previous = bucket.get(key)
        if reason is _REASON_UNSET:
            resolved_reason = previous.reason if previous else None
        else:
            resolved_reason = None if reason is None else str(reason).strip() or None
        record = EdgeOverrideRecord(
            src_node_id=src_node_id,
            dst_node_id=dst_node_id,
            active=bool(active),
            updated_at=self._now(),
            reason=resolved_reason,
        )
        bucket[key] = record
        self._emit_audit(
            world_id,
            {
                "event": "edge_override_upserted",
                "src_node_id": src_node_id,
                "dst_node_id": dst_node_id,
                "active": bool(active),
                "reason": resolved_reason,
                "updated_at": record.updated_at,
            },
        )
        return record

    def get(self, world_id: str, src_node_id: str, dst_node_id: str) -> Optional[EdgeOverrideRecord]:
        bucket = self.overrides.get(world_id)
        if not bucket:
            return None
        record = bucket.get((src_node_id, dst_node_id))
        return None if record is None else record.clone()

    def list(self, world_id: str) -> list[EdgeOverrideRecord]:
        bucket = self.overrides.get(world_id)
        if not bucket:
            return []
        return [payload.clone() for payload in (bucket[key] for key in sorted(bucket.keys()))]

    def delete(self, world_id: str, src_node_id: str, dst_node_id: str) -> None:
        bucket = self.overrides.get(world_id)
        if not bucket:
            return
        record = bucket.pop((src_node_id, dst_node_id), None)
        if record is None:
            return
        if not bucket:
            self.overrides.pop(world_id, None)
        self._emit_audit(
            world_id,
            {
                "event": "edge_override_deleted",
                "src_node_id": src_node_id,
                "dst_node_id": dst_node_id,
                "active": record.active,
            },
        )

    async def ensure_defaults(self, world_id: str) -> None:
        for src_node_id, dst_node_id, reason in DEFAULT_EDGE_OVERRIDES:
            existing = self.get(world_id, src_node_id, dst_node_id)
            if existing is None:
                self.upsert(world_id, src_node_id, dst_node_id, active=False, reason=reason)

    def clear(self, world_id: str) -> None:
        self.overrides.pop(world_id, None)


# Sentinel reused by the facade for compatibility with legacy behaviour.
_REASON_UNSET = object()


__all__ = ["EdgeOverrideRepository", "_REASON_UNSET"]
