from __future__ import annotations

from qmtl.services.worldservice.storage.audit import AuditLogRepository
from qmtl.services.worldservice.storage.edge_overrides import EdgeOverrideRepository, _REASON_UNSET


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
