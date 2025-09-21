from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Set
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
class WorldNodeRefRecord:
    """Dataclass representing a WVG WorldNodeRef entry."""

    world_id: str
    node_id: str
    execution_domain: str
    status: str = "unknown"
    last_eval_key: Optional[str] = None
    annotations: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "world_id": self.world_id,
            "node_id": self.node_id,
            "execution_domain": self.execution_domain,
            "status": self.status,
            "last_eval_key": self.last_eval_key,
            "annotations": self.annotations,
        }


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
        self.world_node_refs: Dict[tuple[str, str, str], WorldNodeRefRecord] = {}
        self._legacy_world_node_refs: Dict[tuple[str, str], List[Dict[str, Any]]] = {}
        self._node_ref_migration_config: Dict[str, Any] = {
            "default_domain": "live",
            "domain_resolver": None,
            "metadata_resolver": None,
        }

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

    async def load_legacy_world_node_refs(
        self,
        records: Iterable[Mapping[str, Any]],
        *,
        default_domain: str = "live",
        domain_resolver: Callable[[Mapping[str, Any]], str] | None = None,
        metadata_resolver: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
    ) -> None:
        """Load legacy WorldNodeRef rows lacking ``execution_domain``."""

        self._legacy_world_node_refs.clear()
        for record in records:
            key = (str(record["world_id"]), str(record["node_id"]))
            bucket = self._legacy_world_node_refs.setdefault(key, [])
            bucket.append(dict(record))
        self._node_ref_migration_config = {
            "default_domain": default_domain,
            "domain_resolver": domain_resolver,
            "metadata_resolver": metadata_resolver,
        }

    async def backfill_world_node_refs(self) -> List[Dict[str, Any]]:
        """Eagerly migrate loaded legacy rows into ``execution_domain`` aware entries."""

        migrated: List[WorldNodeRefRecord] = []
        for key, records in list(self._legacy_world_node_refs.items()):
            for record in list(records):
                upgraded = self._upgrade_legacy_world_node_ref(record, mode="backfill")
                if upgraded:
                    migrated.append(upgraded)
                    records.remove(record)
            if not records:
                self._legacy_world_node_refs.pop(key, None)
        return [item.to_dict() for item in migrated]

    async def get_world_node_ref(
        self,
        world_id: str,
        node_id: str,
        execution_domain: str,
    ) -> Optional[Dict[str, Any]]:
        record = self.world_node_refs.get((world_id, node_id, execution_domain))
        if record:
            return record.to_dict()

        legacy_bucket = self._legacy_world_node_refs.get((world_id, node_id))
        if not legacy_bucket:
            return None
        for legacy in list(legacy_bucket):
            resolved_domain = self._resolve_domain(legacy)
            if resolved_domain != execution_domain:
                continue
            upgraded = self._upgrade_legacy_world_node_ref(
                legacy, mode="lazy", explicit_domain=resolved_domain
            )
            if upgraded:
                legacy_bucket.remove(legacy)
                if not legacy_bucket:
                    self._legacy_world_node_refs.pop((world_id, node_id), None)
                return upgraded.to_dict()
        return None

    async def list_world_node_refs(
        self,
        world_id: str,
        *,
        execution_domain: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        records: List[WorldNodeRefRecord] = []
        for (wid, _, domain), record in self.world_node_refs.items():
            if wid != world_id:
                continue
            if execution_domain and execution_domain != domain:
                continue
            records.append(record)

        for (wid, node_id), bucket in list(self._legacy_world_node_refs.items()):
            if wid != world_id:
                continue
            for legacy in list(bucket):
                resolved_domain = self._resolve_domain(legacy)
                if execution_domain and execution_domain != resolved_domain:
                    continue
                upgraded = self._upgrade_legacy_world_node_ref(legacy, mode="lazy", explicit_domain=resolved_domain)
                if upgraded:
                    records.append(upgraded)
                    bucket.remove(legacy)
            if not bucket:
                self._legacy_world_node_refs.pop((wid, node_id), None)

        return [rec.to_dict() for rec in sorted(records, key=lambda r: (r.node_id, r.execution_domain))]

    @staticmethod
    def compute_eval_key(
        *,
        node_id: str,
        world_id: str,
        execution_domain: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> str:
        payload_items = [
            str(node_id),
            str(world_id),
            str(execution_domain),
        ]
        meta = metadata or {}
        payload_items.extend(
            str(meta.get(key, ""))
            for key in ("contract_id", "dataset_fingerprint", "code_version", "resource_policy")
        )
        payload = "\x1f".join(payload_items).encode("utf-8")
        return hash_bytes(payload)

    def _resolve_domain(self, record: Mapping[str, Any], *, explicit: Optional[str] = None) -> str:
        if explicit:
            return explicit
        domain = record.get("execution_domain")
        if isinstance(domain, str) and domain:
            return domain
        resolver = self._node_ref_migration_config.get("domain_resolver")
        if callable(resolver):
            resolved = resolver(record)
            if resolved:
                return resolved
        return str(self._node_ref_migration_config.get("default_domain", "live"))

    def _resolve_metadata(self, record: Mapping[str, Any]) -> Dict[str, Any]:
        annotations = record.get("annotations")
        meta: Dict[str, Any]
        if isinstance(annotations, Mapping):
            meta = dict(annotations)
        else:
            meta = {}
        resolver = self._node_ref_migration_config.get("metadata_resolver")
        if callable(resolver):
            extra = resolver(record)
            if extra:
                meta.update(dict(extra))
        return meta

    def _upgrade_legacy_world_node_ref(
        self,
        record: Mapping[str, Any],
        *,
        mode: str,
        explicit_domain: Optional[str] = None,
    ) -> Optional[WorldNodeRefRecord]:
        world_id = str(record.get("world_id"))
        node_id = str(record.get("node_id"))
        if not world_id or not node_id:
            return None
        domain = self._resolve_domain(record, explicit=explicit_domain)
        metadata = self._resolve_metadata(record)
        eval_key = self.compute_eval_key(
            node_id=node_id,
            world_id=world_id,
            execution_domain=domain,
            metadata=metadata,
        )
        annotations = metadata or None
        upgraded = WorldNodeRefRecord(
            world_id=world_id,
            node_id=node_id,
            execution_domain=domain,
            status=str(record.get("status", "unknown")),
            last_eval_key=eval_key,
            annotations=annotations,
        )
        self.world_node_refs[(world_id, node_id, domain)] = upgraded
        self.audit.setdefault(world_id, WorldAuditLog()).entries.append(
            {
                "event": "world_node_ref_migrated",
                "node_id": node_id,
                "execution_domain": domain,
                "mode": mode,
                "previous_eval_key": record.get("last_eval_key"),
                "new_eval_key": eval_key,
            }
        )
        return upgraded


__all__ = [
    'WorldActivation',
    'WorldPolicies',
    'WorldAuditLog',
    'WorldNodeRefRecord',
    'Storage',
]
