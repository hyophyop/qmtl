from __future__ import annotations

from qmtl.services.worldservice.storage.audit import AuditLogRepository


def test_audit_repository_round_trip() -> None:
    repo = AuditLogRepository()

    repo.append("world-1", {"event": "created"})
    repo.append("world-1", {"event": "updated"})

    entries = repo.list_entries("world-1")
    assert entries == [{"event": "created"}, {"event": "updated"}]
    assert repo.get("world-1").entries[0]["event"] == "created"

    repo.clear("world-1")
    assert repo.list_entries("world-1") == []
