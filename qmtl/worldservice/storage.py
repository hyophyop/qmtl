from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Set

from .policy_engine import Policy


@dataclass
class WorldActivation:
    """Activation state for a world."""

    version: int = 0
    state: Dict[str, Dict[str, float | bool]] = field(default_factory=dict)


@dataclass
class WorldPolicies:
    """Policy versions for a world."""

    versions: Dict[int, Policy] = field(default_factory=dict)
    default: Optional[int] = None


@dataclass
class WorldAuditLog:
    """Audit entries for a world."""

    entries: List[Dict] = field(default_factory=list)


class Storage:
    """In-memory storage backing WorldService endpoints.

    This lightweight layer mimics Redis/DB backed models for tests.
    """

    def __init__(self) -> None:
        self.worlds: Dict[str, Dict] = {}
        self.activations: Dict[str, WorldActivation] = {}
        self.policies: Dict[str, WorldPolicies] = {}
        self.bindings: Dict[str, Set[str]] = {}
        self.decisions: Dict[str, List[str]] = {}
        self.audit: Dict[str, WorldAuditLog] = {}

    async def create_world(self, world: Dict) -> None:
        self.worlds[world["id"]] = world
        self.audit.setdefault(world["id"], WorldAuditLog()).entries.append({"event": "world_created", "world": world})

    async def list_worlds(self) -> List[Dict]:
        return list(self.worlds.values())

    async def get_world(self, world_id: str) -> Optional[Dict]:
        return self.worlds.get(world_id)

    async def update_world(self, world_id: str, data: Dict) -> None:
        if world_id not in self.worlds:
            raise KeyError(world_id)
        self.worlds[world_id].update(data)
        self.audit.setdefault(world_id, WorldAuditLog()).entries.append({"event": "world_updated", "world": self.worlds[world_id]})

    async def delete_world(self, world_id: str) -> None:
        self.worlds.pop(world_id, None)
        self.activations.pop(world_id, None)
        self.policies.pop(world_id, None)
        self.bindings.pop(world_id, None)
        self.decisions.pop(world_id, None)
        self.audit.setdefault(world_id, WorldAuditLog()).entries.append({"event": "world_deleted"})

    async def add_policy(self, world_id: str, policy: Policy) -> int:
        wp = self.policies.setdefault(world_id, WorldPolicies())
        version = max(wp.versions.keys(), default=0) + 1
        wp.versions[version] = policy
        if wp.default is None:
            wp.default = version
        self.audit.setdefault(world_id, WorldAuditLog()).entries.append({"event": "policy_added", "version": version})
        return version

    async def list_policies(self, world_id: str) -> List[Dict]:
        wp = self.policies.get(world_id)
        if not wp:
            return []
        return [{"version": v} for v in sorted(wp.versions.keys())]

    async def get_policy(self, world_id: str, version: int) -> Optional[Policy]:
        wp = self.policies.get(world_id)
        if not wp:
            return None
        return wp.versions.get(version)

    async def set_default_policy(self, world_id: str, version: int) -> None:
        wp = self.policies.setdefault(world_id, WorldPolicies())
        if version not in wp.versions:
            raise KeyError(version)
        wp.default = version
        self.audit.setdefault(world_id, WorldAuditLog()).entries.append({"event": "policy_default_set", "version": version})

    async def get_default_policy(self, world_id: str) -> Optional[Policy]:
        wp = self.policies.get(world_id)
        if not wp or wp.default is None:
            return None
        return wp.versions.get(wp.default)

    async def default_policy_version(self, world_id: str) -> int:
        wp = self.policies.get(world_id)
        if not wp or wp.default is None:
            return 0
        return wp.default

    async def add_bindings(self, world_id: str, strategies: Iterable[str]) -> None:
        b = self.bindings.setdefault(world_id, set())
        b.update(strategies)
        self.audit.setdefault(world_id, WorldAuditLog()).entries.append({"event": "bindings_added", "strategies": list(strategies)})

    async def list_bindings(self, world_id: str) -> List[str]:
        return sorted(self.bindings.get(world_id, set()))

    async def set_decisions(self, world_id: str, strategies: List[str]) -> None:
        self.decisions[world_id] = list(strategies)
        self.audit.setdefault(world_id, WorldAuditLog()).entries.append({"event": "decisions_set", "strategies": list(strategies)})

    async def get_decisions(self, world_id: str) -> List[str]:
        return list(self.decisions.get(world_id, []))

    async def get_activation(self, world_id: str) -> Dict:
        act = self.activations.get(world_id)
        if not act:
            return {"version": 0, "state": {}}
        return {"version": act.version, **act.state}

    async def update_activation(self, world_id: str, payload: Dict) -> int:
        act = self.activations.setdefault(world_id, WorldActivation())
        act.version += 1
        act.state.update(payload)
        self.audit.setdefault(world_id, WorldAuditLog()).entries.append({"event": "activation_updated", "version": act.version, **payload})
        return act.version

    async def get_audit(self, world_id: str) -> List[Dict]:
        return list(self.audit.get(world_id, WorldAuditLog()).entries)


__all__ = [
    'WorldActivation',
    'WorldPolicies',
    'WorldAuditLog',
    'Storage',
]
