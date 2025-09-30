"""World repository implementation."""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

from .auditable import AuditableRepository, AuditSink
from .models import WorldRecord


class WorldRepository(AuditableRepository):
    """CRUD around worlds."""

    def __init__(self, audit: AuditSink) -> None:
        super().__init__(audit)
        self.records: Dict[str, WorldRecord] = {}

    def create(self, payload: Mapping[str, Any]) -> WorldRecord:
        record = WorldRecord.from_payload(payload)
        self.records[record.id] = record
        self._emit_audit(record.id, {"event": "world_created", "world": record.to_dict()})
        return record

    def list(self) -> list[Dict[str, Any]]:
        return [record.to_dict() for record in self.records.values()]

    def get(self, world_id: str) -> Optional[Dict[str, Any]]:
        record = self.records.get(world_id)
        if record is None:
            return None
        return record.to_dict()

    def update(self, world_id: str, payload: Mapping[str, Any]) -> WorldRecord:
        if world_id not in self.records:
            raise KeyError(world_id)
        record = self.records[world_id]
        record.update(payload)
        self._emit_audit(world_id, {"event": "world_updated", "world": record.to_dict()})
        return record

    def delete(self, world_id: str) -> None:
        self.records.pop(world_id, None)
        self._emit_audit(world_id, {"event": "world_deleted"})


__all__ = ["WorldRepository"]
