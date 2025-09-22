from __future__ import annotations

import pytest

from qmtl.worldservice.storage.audit import AuditLogRepository
from qmtl.worldservice.storage.nodes import WorldNodeRepository


@pytest.mark.parametrize("domain", ["BACKTEST", "Backtest", "backtest"])
def test_world_node_repository_normalises_domain(domain: str) -> None:
    audit = AuditLogRepository()
    repo = WorldNodeRepository(audit)

    record = repo.upsert(
        "world-1",
        "node-1",
        execution_domain=domain,
        status="running",
        annotations={"note": "value"},
    )

    assert record["execution_domain"] == "backtest"
    assert record["status"] == "running"
    assert repo.get("world-1", "node-1", execution_domain="backtest") == record

    entries = repo.list("world-1", execution_domain="*")
    assert entries == [record]

    audit_events = [event["event"] for event in audit.list_entries("world-1")]
    assert audit_events[-1] == "world_node_upserted"
