"""Repository maintaining decision snapshots."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Dict

from .auditable import AuditableRepository, AuditSink


class DecisionRepository(AuditableRepository):
    """Maintains decision snapshots for a world."""

    def __init__(self, audit: AuditSink) -> None:
        super().__init__(audit)
        self.decisions: Dict[str, list[str]] = {}

    def set(self, world_id: str, strategies: Iterable[str]) -> None:
        sequence = list(strategies)
        self.decisions[world_id] = sequence
        self._emit_audit(world_id, {"event": "decisions_set", "strategies": sequence})

    def get(self, world_id: str) -> list[str]:
        return list(self.decisions.get(world_id, []))

    def clear(self, world_id: str) -> None:
        self.decisions.pop(world_id, None)


__all__ = ["DecisionRepository"]
