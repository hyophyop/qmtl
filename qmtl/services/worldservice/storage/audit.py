"""Audit repository supporting the in-memory WorldService storage."""

from __future__ import annotations

from typing import Any, Dict, Mapping

from .models import WorldAuditLog


class AuditLogRepository:
    """Stores audit events per world."""

    def __init__(self) -> None:
        self.logs: Dict[str, WorldAuditLog] = {}

    def append(self, world_id: str, entry: Mapping[str, Any]) -> None:
        self.logs.setdefault(world_id, WorldAuditLog()).entries.append(dict(entry))

    def get(self, world_id: str) -> WorldAuditLog:
        return self.logs.setdefault(world_id, WorldAuditLog())

    def list_entries(self, world_id: str) -> list[Dict[str, Any]]:
        return list(self.get(world_id).entries)

    def clear(self, world_id: str) -> None:
        self.logs.pop(world_id, None)


__all__ = ["AuditLogRepository"]
