from __future__ import annotations

from itertools import cycle

from qmtl.services.worldservice.storage import models
from qmtl.services.worldservice.storage.audit import AuditLogRepository
from qmtl.services.worldservice.storage.worlds import WorldRepository


def test_world_repository_persists_records_and_audits(monkeypatch) -> None:
    timestamps = cycle([
        "2025-01-01T00:00:00Z",
        "2025-01-02T00:00:00Z",
        "2025-01-03T00:00:00Z",
    ])
    monkeypatch.setattr(models, "_iso_timestamp", lambda: next(timestamps))

    audit = AuditLogRepository()
    repo = WorldRepository(audit)

    record = repo.create({
        "id": "world-1",
        "name": "First",
        "labels": ["core", "beta"],
        "contract_id": "cid-1",
    })
    assert record.id == "world-1"
    assert repo.get("world-1") == {
        "id": "world-1",
        "name": "First",
        "description": None,
        "owner": None,
        "labels": ["core", "beta"],
        "state": "ACTIVE",
        "allow_live": False,
        "circuit_breaker": False,
        "default_policy_version": None,
        "created_at": "2025-01-01T00:00:00Z",
        "updated_at": "2025-01-01T00:00:00Z",
        "contract_id": "cid-1",
    }

    repo.update(
        "world-1",
        {
            "description": "primary",
            "owner": "alice",
            "allow_live": True,
            "labels": ["core", "stable"],
        },
    )
    assert repo.get("world-1") == {
        "id": "world-1",
        "name": "First",
        "description": "primary",
        "owner": "alice",
        "labels": ["core", "stable"],
        "state": "ACTIVE",
        "allow_live": True,
        "circuit_breaker": False,
        "default_policy_version": None,
        "created_at": "2025-01-01T00:00:00Z",
        "updated_at": "2025-01-02T00:00:00Z",
        "contract_id": "cid-1",
    }

    entries = audit.list_entries("world-1")
    assert [event["event"] for event in entries] == ["world_created", "world_updated"]
    assert entries[0]["world"]["created_at"] == "2025-01-01T00:00:00Z"
    assert entries[1]["world"]["updated_at"] == "2025-01-02T00:00:00Z"


def test_world_update_ignores_none_created_at(monkeypatch) -> None:
    timestamps = cycle([
        "2025-01-01T00:00:00Z",
        "2025-01-02T00:00:00Z",
    ])
    monkeypatch.setattr(models, "_iso_timestamp", lambda: next(timestamps))

    audit = AuditLogRepository()
    repo = WorldRepository(audit)

    record = repo.create({
        "id": "world-2",
        "name": "Second",
    })

    repo.update(
        "world-2",
        {
            "created_at": None,
            "description": "updated",
        },
    )

    assert record.created_at == "2025-01-01T00:00:00Z"
    assert record.updated_at == "2025-01-02T00:00:00Z"
    assert record.description == "updated"
