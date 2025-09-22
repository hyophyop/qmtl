from __future__ import annotations

import pytest

from qmtl.worldservice.storage.models import ValidationCacheEntry
from qmtl.worldservice.storage.repositories import (
    AuditLogRepository,
    EdgeOverrideRepository,
    ValidationCacheRepository,
    WorldRepository,
    _REASON_UNSET,
)


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


def test_edge_override_repository_reason_round_trip() -> None:
    audit = AuditLogRepository()
    repo = EdgeOverrideRepository(audit)

    created = repo.upsert(
        "world-1",
        "domain:backtest",
        "domain:live",
        active=False,
        reason="auto:block",
    )
    assert created.reason == "auto:block"

    preserved = repo.upsert(
        "world-1",
        "domain:backtest",
        "domain:live",
        active=True,
        reason=_REASON_UNSET,
    )
    assert preserved.reason == "auto:block"

    repo.delete("world-1", "domain:backtest", "domain:live")
    events = audit.list_entries("world-1")
    assert [event["event"] for event in events] == [
        "edge_override_upserted",
        "edge_override_upserted",
        "edge_override_deleted",
    ]


@pytest.mark.parametrize("domain", ["BACKTEST", "Backtest", "backtest"])
def test_validation_cache_repository_normalises_domain(domain: str) -> None:
    audit = AuditLogRepository()
    repo = ValidationCacheRepository(audit)

    repo.set(
        "world-1",
        node_id="node-1",
        execution_domain=domain,
        contract_id="contract",
        dataset_fingerprint="fp",
        code_version="v1",
        resource_policy="default",
        result="ok",
        metrics={"latency": 1.0},
    )

    legacy_key = repo._compute_eval_key(  # type: ignore[attr-defined]
        node_id="node-1",
        world_id="world-1",
        execution_domain="backtest",
        contract_id="contract",
        dataset_fingerprint="fp",
        code_version="v1",
        resource_policy="default",
    )
    legacy = ValidationCacheEntry(
        eval_key=legacy_key,
        node_id="node-1",
        execution_domain="BACKTEST",
        contract_id="contract",
        dataset_fingerprint="fp",
        code_version="v1",
        resource_policy="default",
        result="ok",
        metrics={"latency": 1.0},
        timestamp="2024-01-01T00:00:00Z",
    )
    repo.cache.setdefault("world-1", {}).setdefault("node-1", {})["BACKTEST"] = legacy

    entry = repo.get(
        "world-1",
        node_id="node-1",
        execution_domain="backtest",
        contract_id="contract",
        dataset_fingerprint="fp",
        code_version="v1",
        resource_policy="default",
    )
    assert entry is not None
    assert entry.execution_domain == "backtest"
