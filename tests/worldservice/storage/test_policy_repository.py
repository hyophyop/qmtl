from __future__ import annotations

import pytest

from qmtl.worldservice.storage.audit import AuditLogRepository
from qmtl.worldservice.storage.policies import PolicyRepository


def test_policy_repository_tracks_versions() -> None:
    audit = AuditLogRepository()
    repo = PolicyRepository(audit)

    first = repo.add("world-1", {"rules": []})
    second = repo.add("world-1", {"rules": ["beta"]})

    assert first.version == 1
    assert second.version == 2
    assert repo.default_version("world-1") == 1

    repo.set_default("world-1", 2)
    assert repo.default_version("world-1") == 2
    assert repo.get_default("world-1") == {"rules": ["beta"]}
    assert repo.list_versions("world-1") == [{"version": 1}, {"version": 2}]

    with pytest.raises(KeyError):
        repo.set_default("world-1", 99)

    events = [entry["event"] for entry in audit.list_entries("world-1")]
    assert events == ["policy_added", "policy_added", "policy_default_set"]
