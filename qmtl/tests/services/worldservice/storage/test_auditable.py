from __future__ import annotations

from typing import Any, Mapping

from qmtl.services.worldservice.storage.auditable import AuditableRepository, AuditSink


class _Recorder(AuditSink):  # type: ignore[misc]
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    def append(self, world_id: str, entry: Mapping[str, Any]) -> None:
        self.events.append((world_id, dict(entry)))


class _SampleRepository(AuditableRepository):
    def emit(self, world_id: str, payload: Mapping[str, Any]) -> None:
        self._emit_audit(world_id, payload)


def test_auditable_repository_emits_copy() -> None:
    audit = _Recorder()
    repo = _SampleRepository(audit)

    payload = {"event": "demo", "meta": {"key": "value"}}
    repo.emit("world-1", payload)

    assert audit.events == [("world-1", {"event": "demo", "meta": {"key": "value"}})]
    assert audit.events[0][1] is not payload
