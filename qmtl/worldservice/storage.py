from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Set
from datetime import datetime, timezone

from .policy_engine import Policy
from qmtl.common.hashutils import hash_bytes


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


@dataclass
class ValidationCacheEntry:
    """Cached validation result scoped by ExecutionDomain."""

    eval_key: str
    node_id: str
    execution_domain: str
    contract_id: str
    dataset_fingerprint: str
    code_version: str
    resource_policy: str
    result: str
    metrics: Dict[str, Any]
    timestamp: str


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
        self.validation_cache: Dict[str, Dict[str, Dict[str, ValidationCacheEntry]]] = {}

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
        if {"contract_id", "dataset_fingerprint", "resource_policy", "code_version"} & data.keys():
            await self.invalidate_validation_cache(world_id)

    async def delete_world(self, world_id: str) -> None:
        self.worlds.pop(world_id, None)
        self.activations.pop(world_id, None)
        self.policies.pop(world_id, None)
        self.bindings.pop(world_id, None)
        self.decisions.pop(world_id, None)
        self.validation_cache.pop(world_id, None)
        self.audit.setdefault(world_id, WorldAuditLog()).entries.append({"event": "world_deleted"})

    async def add_policy(self, world_id: str, policy: Policy) -> int:
        wp = self.policies.setdefault(world_id, WorldPolicies())
        version = max(wp.versions.keys(), default=0) + 1
        wp.versions[version] = policy
        if wp.default is None:
            wp.default = version
        self.audit.setdefault(world_id, WorldAuditLog()).entries.append({"event": "policy_added", "version": version})
        await self.invalidate_validation_cache(world_id)
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
        await self.invalidate_validation_cache(world_id)

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

    def _compute_eval_key(
        self,
        *,
        node_id: str,
        world_id: str,
        execution_domain: str,
        contract_id: str,
        dataset_fingerprint: str,
        code_version: str,
        resource_policy: str,
    ) -> str:
        components = [
            node_id,
            world_id,
            execution_domain,
            contract_id,
            dataset_fingerprint,
            code_version,
            resource_policy,
        ]
        payload = "\x1f".join(str(part) for part in components).encode()
        return hash_bytes(payload)

    async def get_validation_cache(
        self,
        world_id: str,
        *,
        node_id: str,
        execution_domain: str,
        contract_id: str,
        dataset_fingerprint: str,
        code_version: str,
        resource_policy: str,
    ) -> Optional[ValidationCacheEntry]:
        world_cache = self.validation_cache.get(world_id)
        if not world_cache:
            return None
        node_cache = world_cache.get(node_id)
        if not node_cache:
            return None
        entry = node_cache.get(execution_domain)
        if not entry:
            return None
        expected_key = self._compute_eval_key(
            node_id=node_id,
            world_id=world_id,
            execution_domain=execution_domain,
            contract_id=contract_id,
            dataset_fingerprint=dataset_fingerprint,
            code_version=code_version,
            resource_policy=resource_policy,
        )
        if entry.eval_key != expected_key:
            node_cache.pop(execution_domain, None)
            if not node_cache:
                world_cache.pop(node_id, None)
            if not world_cache:
                self.validation_cache.pop(world_id, None)
            self.audit.setdefault(world_id, WorldAuditLog()).entries.append(
                {
                    "event": "validation_cache_invalidated",
                    "reason": "context_mismatch",
                    "node_id": node_id,
                    "execution_domain": execution_domain,
                    "stored_eval_key": entry.eval_key,
                    "expected_eval_key": expected_key,
                }
            )
            return None
        return entry

    async def set_validation_cache(
        self,
        world_id: str,
        *,
        node_id: str,
        execution_domain: str,
        contract_id: str,
        dataset_fingerprint: str,
        code_version: str,
        resource_policy: str,
        result: str,
        metrics: Dict[str, Any],
        timestamp: str | None = None,
    ) -> ValidationCacheEntry:
        eval_key = self._compute_eval_key(
            node_id=node_id,
            world_id=world_id,
            execution_domain=execution_domain,
            contract_id=contract_id,
            dataset_fingerprint=dataset_fingerprint,
            code_version=code_version,
            resource_policy=resource_policy,
        )
        ts = (
            timestamp
            or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        )
        entry = ValidationCacheEntry(
            eval_key=eval_key,
            node_id=node_id,
            execution_domain=execution_domain,
            contract_id=contract_id,
            dataset_fingerprint=dataset_fingerprint,
            code_version=code_version,
            resource_policy=resource_policy,
            result=result,
            metrics=dict(metrics),
            timestamp=ts,
        )
        world_cache = self.validation_cache.setdefault(world_id, {})
        node_cache = world_cache.setdefault(node_id, {})
        node_cache[execution_domain] = entry
        self.audit.setdefault(world_id, WorldAuditLog()).entries.append(
            {
                "event": "validation_cached",
                "node_id": node_id,
                "execution_domain": execution_domain,
                "eval_key": eval_key,
            }
        )
        return entry

    async def invalidate_validation_cache(
        self,
        world_id: str,
        *,
        node_id: str | None = None,
        execution_domain: str | None = None,
    ) -> None:
        cache = self.validation_cache.get(world_id)
        if not cache:
            return
        if node_id is None:
            self.validation_cache.pop(world_id, None)
            scope = {"scope": "world"}
        else:
            node_cache = cache.get(node_id)
            if not node_cache:
                return
            if execution_domain is None:
                cache.pop(node_id, None)
                scope = {"scope": "node", "node_id": node_id}
            else:
                node_cache.pop(execution_domain, None)
                if not node_cache:
                    cache.pop(node_id, None)
                scope = {
                    "scope": "domain",
                    "node_id": node_id,
                    "execution_domain": execution_domain,
                }
            if not cache:
                self.validation_cache.pop(world_id, None)
        self.audit.setdefault(world_id, WorldAuditLog()).entries.append(
            {"event": "validation_cache_cleared", **scope}
        )

    async def get_activation(self, world_id: str, strategy_id: str | None = None, side: str | None = None) -> Dict:
        act = self.activations.get(world_id)
        if not act:
            return {"version": 0, "state": {}}
        if strategy_id is not None and side is not None:
            data = act.state.get(strategy_id, {}).get(side, {})
            return {"version": act.version, **data}
        return {"version": act.version, "state": act.state}

    async def update_activation(self, world_id: str, payload: Dict) -> tuple[int, Dict]:
        act = self.activations.setdefault(world_id, WorldActivation())
        act.version += 1
        strategy_id = payload["strategy_id"]
        side = payload["side"]
        entry = {
            "active": payload.get("active", False),
            "weight": payload.get("weight", 1.0),
            "freeze": payload.get("freeze", False),
            "drain": payload.get("drain", False),
            "effective_mode": payload.get("effective_mode"),
            "run_id": payload.get("run_id"),
            "ts": payload.get("ts")
            or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        }
        etag = f"act:{world_id}:{strategy_id}:{side}:{act.version}"
        entry["etag"] = etag
        act.state.setdefault(strategy_id, {})[side] = entry
        self.audit.setdefault(world_id, WorldAuditLog()).entries.append(
            {"event": "activation_updated", "version": act.version, "strategy_id": strategy_id, "side": side, **entry}
        )
        return act.version, entry

    async def get_audit(self, world_id: str) -> List[Dict]:
        return list(self.audit.get(world_id, WorldAuditLog()).entries)


__all__ = [
    'WorldActivation',
    'WorldPolicies',
    'WorldAuditLog',
    'ValidationCacheEntry',
    'Storage',
]
