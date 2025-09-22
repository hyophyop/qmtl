from __future__ import annotations

from qmtl.worldservice.storage.audit import AuditLogRepository
from qmtl.worldservice.storage.worlds import WorldRepository


def test_world_repository_persists_records_and_audits() -> None:
    audit = AuditLogRepository()
    repo = WorldRepository(audit)

    record = repo.create({"id": "world-1", "name": "First"})
    assert record.id == "world-1"
    assert repo.get("world-1") == {"id": "world-1", "name": "First"}

    repo.update("world-1", {"description": "primary"})
    assert repo.get("world-1") == {
        "id": "world-1",
        "name": "First",
        "description": "primary",
    }

    entries = audit.list_entries("world-1")
    assert [event["event"] for event in entries] == [
        "world_created",
        "world_updated",
    ]
