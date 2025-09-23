from __future__ import annotations

from qmtl.services.worldservice.storage.audit import AuditLogRepository
from qmtl.services.worldservice.storage.bindings import BindingRepository


def test_binding_repository_merges_strategies() -> None:
    audit = AuditLogRepository()
    repo = BindingRepository(audit)

    repo.add("world-1", ["alpha", "beta"])
    repo.add("world-1", ["beta", "gamma"])

    assert repo.list("world-1") == ["alpha", "beta", "gamma"]
    events = audit.list_entries("world-1")
    assert [event["event"] for event in events] == ["bindings_added", "bindings_added"]
