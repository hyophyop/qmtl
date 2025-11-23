from __future__ import annotations

import pytest

from qmtl.services.worldservice.storage.audit import AuditLogRepository
from qmtl.services.worldservice.storage.nodes import WorldNodeRepository


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


def test_world_node_repository_normalizes_legacy_bucket() -> None:
    audit = AuditLogRepository()
    repo = WorldNodeRepository(audit)

    repo.nodes["world-legacy"] = {
        "node-legacy": {
            "execution_domain": "Live",
            "status": "running",
            "last_eval_key": "eval-1",
            "annotations": {"note": True},
        }
    }

    record = repo.get("world-legacy", "node-legacy", execution_domain="live")

    assert record == {
        "world_id": "world-legacy",
        "node_id": "node-legacy",
        "execution_domain": "live",
        "status": "running",
        "last_eval_key": "eval-1",
        "annotations": {"note": True},
    }
    normalized_bucket = repo.nodes["world-legacy"]["node-legacy"]
    assert set(normalized_bucket.keys()) == {"live"}
    assert audit.list_entries("world-legacy")[-1]["event"] == "world_node_bucket_normalized"


def test_world_node_repository_bucket_normalization_and_filters() -> None:
    audit = AuditLogRepository()
    repo = WorldNodeRepository(audit)

    repo.nodes["world-bucket"] = {
        "node-1": {
            "Backtest": {"status": "running"},
            "prod": {"execution_domain": "Live", "status": "valid"},
        }
    }

    all_domains = repo.list("world-bucket", execution_domain="all")
    assert {entry["execution_domain"] for entry in all_domains} == {"backtest", "live"}

    filtered = repo.list("world-bucket", execution_domain="backtest")
    assert filtered == [
        {
            "world_id": "world-bucket",
            "node_id": "node-1",
            "execution_domain": "backtest",
            "status": "running",
            "last_eval_key": None,
            "annotations": None,
        }
    ]

    audit_events = [entry["event"] for entry in audit.list_entries("world-bucket")]
    assert audit_events[-1] == "world_node_bucket_normalized"
