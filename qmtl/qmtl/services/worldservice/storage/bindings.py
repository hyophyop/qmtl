"""Repository for strategy bindings."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Dict

from .auditable import AuditableRepository, AuditSink


class BindingRepository(AuditableRepository):
    """Stores strategy bindings."""

    def __init__(self, audit: AuditSink) -> None:
        super().__init__(audit)
        self.bindings: Dict[str, set[str]] = {}

    def add(self, world_id: str, strategies: Iterable[str]) -> None:
        bucket = self.bindings.setdefault(world_id, set())
        sequence = list(strategies)
        bucket.update(sequence)
        self._emit_audit(world_id, {"event": "bindings_added", "strategies": sequence})

    def list(self, world_id: str) -> list[str]:
        return sorted(self.bindings.get(world_id, set()))

    def clear(self, world_id: str) -> None:
        self.bindings.pop(world_id, None)


__all__ = ["BindingRepository"]
