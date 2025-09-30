from __future__ import annotations

from qmtl.services.worldservice.storage.activations import ActivationRepository
from qmtl.services.worldservice.storage.audit import AuditLogRepository


def test_activation_repository_updates_state() -> None:
    audit = AuditLogRepository()
    repo = ActivationRepository(audit)

    version, entry = repo.update(
        "world-1",
        {
            "strategy_id": "alpha",
            "side": "long",
            "active": True,
            "weight": 2.0,
        },
    )

    assert version == 1
    assert entry["active"] is True
    snapshot = repo.snapshot("world-1")
    assert snapshot.state["alpha"]["long"]["active"] is True

    payload = repo.get("world-1", "alpha", "long")
    assert payload["version"] == 1

    events = audit.list_entries("world-1")
    assert events[0]["event"] == "activation_updated"
