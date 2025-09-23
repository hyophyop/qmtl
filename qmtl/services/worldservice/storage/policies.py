"""Policy repository implementation."""

from __future__ import annotations

from typing import Any, Dict

from .auditable import AuditableRepository, AuditSink
from .models import PolicyVersion, WorldPolicies


class PolicyRepository(AuditableRepository):
    """Manages policy revisions for a world."""

    def __init__(self, audit: AuditSink) -> None:
        super().__init__(audit)
        self._policies: Dict[str, WorldPolicies] = {}

    def add(self, world_id: str, policy: Any) -> PolicyVersion:
        bundle = self._policies.setdefault(world_id, WorldPolicies())
        version = max(bundle.versions.keys(), default=0) + 1
        record = PolicyVersion(version=version, payload=policy)
        bundle.versions[version] = record
        if bundle.default is None:
            bundle.default = version
        self._emit_audit(world_id, {"event": "policy_added", "version": version})
        return record

    def list_versions(self, world_id: str) -> list[Dict[str, int]]:
        bundle = self._policies.get(world_id)
        if not bundle:
            return []
        return [{"version": version} for version in sorted(bundle.versions.keys())]

    def get(self, world_id: str, version: int) -> Any | None:
        bundle = self._policies.get(world_id)
        if not bundle:
            return None
        record = bundle.versions.get(version)
        return None if record is None else record.payload

    def set_default(self, world_id: str, version: int) -> None:
        bundle = self._policies.setdefault(world_id, WorldPolicies())
        if version not in bundle.versions:
            raise KeyError(version)
        bundle.default = version
        self._emit_audit(world_id, {"event": "policy_default_set", "version": version})

    def get_default(self, world_id: str) -> Any | None:
        bundle = self._policies.get(world_id)
        if not bundle or bundle.default is None:
            return None
        record = bundle.versions.get(bundle.default)
        return None if record is None else record.payload

    def default_version(self, world_id: str) -> int:
        bundle = self._policies.get(world_id)
        if not bundle or bundle.default is None:
            return 0
        return bundle.default

    def clear(self, world_id: str) -> None:
        self._policies.pop(world_id, None)


__all__ = ["PolicyRepository"]
