from __future__ import annotations

from qmtl.services.worldservice.storage.audit import AuditLogRepository
from qmtl.services.worldservice.storage.decisions import DecisionRepository


def test_decision_repository_sets_snapshots() -> None:
    audit = AuditLogRepository()
    repo = DecisionRepository(audit)

    repo.set("world-1", ["alpha", "beta"])
    assert repo.get("world-1") == ["alpha", "beta"]

    repo.clear("world-1")
    assert repo.get("world-1") == []

    events = audit.list_entries("world-1")
    assert [event["event"] for event in events] == ["decisions_set"]
