from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple
from datetime import datetime, timezone

from .policy_engine import Policy
from qmtl.common.hashutils import hash_bytes


WORLD_NODE_STATUSES: set[str] = {
    "unknown",
    "validating",
    "valid",
    "invalid",
    "running",
    "paused",
    "stopped",
    "archived",
}
EXECUTION_DOMAINS: set[str] = {"backtest", "dryrun", "live", "shadow"}
DEFAULT_EXECUTION_DOMAIN = "live"
DEFAULT_WORLD_NODE_STATUS = "unknown"

_REASON_UNSET = object()
DEFAULT_EDGE_OVERRIDES: Tuple[tuple[str, str, str]] = (
    ("domain:backtest", "domain:live", "auto:cross-domain-block"),
)


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
        self.world_nodes: Dict[str, Dict[str, Dict[str, Dict[str, Any]]]] = {}
        self.apply_runs: Dict[str, Dict] = {}
        self.validation_cache: Dict[str, Dict[str, Dict[str, ValidationCacheEntry]]] = {}
        self.edge_overrides: Dict[str, Dict[tuple[str, str], Dict[str, Any]]] = {}

    async def create_world(self, world: Dict) -> None:
        self.worlds[world["id"]] = world
        self.audit.setdefault(world["id"], WorldAuditLog()).entries.append({"event": "world_created", "world": world})
        await self._ensure_default_edge_overrides(world["id"])

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
        self.world_nodes.pop(world_id, None)
        self.validation_cache.pop(world_id, None)
        self.edge_overrides.pop(world_id, None)
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
        normalized_domain = self._normalize_execution_domain(execution_domain)
        components = [
            node_id,
            world_id,
            normalized_domain,
            contract_id,
            dataset_fingerprint,
            code_version,
            resource_policy,
        ]
        payload = "\x1f".join(str(part) for part in components).encode()
        return hash_bytes(payload)

    def _coerce_validation_cache_entry(
        self,
        entry: ValidationCacheEntry | Dict[str, Any],
        *,
        world_id: str,
        node_id: str,
        execution_domain: str,
    ) -> Optional[ValidationCacheEntry]:
        if isinstance(entry, ValidationCacheEntry):
            normalized_domain = self._normalize_execution_domain(entry.execution_domain)
            if normalized_domain == entry.execution_domain:
                return entry
            return ValidationCacheEntry(
                eval_key=entry.eval_key,
                node_id=entry.node_id,
                execution_domain=normalized_domain,
                contract_id=entry.contract_id,
                dataset_fingerprint=entry.dataset_fingerprint,
                code_version=entry.code_version,
                resource_policy=entry.resource_policy,
                result=entry.result,
                metrics=dict(entry.metrics),
                timestamp=entry.timestamp,
            )

        if not isinstance(entry, dict):
            raise TypeError(
                f"unexpected validation cache payload for {world_id}/{node_id}: {entry!r}"
            )

        eval_key = entry.get("eval_key")
        contract_id = entry.get("contract_id")
        dataset_fingerprint = entry.get("dataset_fingerprint")
        code_version = entry.get("code_version")
        resource_policy = entry.get("resource_policy")
        result = entry.get("result")
        timestamp = entry.get("timestamp")

        if not isinstance(eval_key, str):
            return None
        if not isinstance(contract_id, str):
            return None
        if not isinstance(dataset_fingerprint, str):
            return None
        if not isinstance(code_version, str):
            return None
        if not isinstance(resource_policy, str):
            return None
        if not isinstance(result, str):
            return None
        if not isinstance(timestamp, str):
            return None

        metrics = entry.get("metrics") or {}
        if not isinstance(metrics, dict):
            metrics = dict(metrics)

        node_value = entry.get("node_id")
        node_value = node_value if isinstance(node_value, str) else node_id

        domain_value = entry.get("execution_domain", execution_domain)
        try:
            normalized_domain = self._normalize_execution_domain(domain_value)
        except ValueError:
            normalized_domain = DEFAULT_EXECUTION_DOMAIN

        return ValidationCacheEntry(
            eval_key=eval_key,
            node_id=node_value,
            execution_domain=normalized_domain,
            contract_id=contract_id,
            dataset_fingerprint=dataset_fingerprint,
            code_version=code_version,
            resource_policy=resource_policy,
            result=result,
            metrics=dict(metrics),
            timestamp=timestamp,
        )

    def _ensure_validation_cache_bucket(
        self, world_id: str, node_id: str
    ) -> Dict[str, ValidationCacheEntry]:
        world_cache = self.validation_cache.setdefault(world_id, {})
        bucket = world_cache.get(node_id)
        if bucket is None:
            bucket = {}
            world_cache[node_id] = bucket
            return bucket
        if not isinstance(bucket, dict):
            raise TypeError(
                f"unexpected validation cache container for {world_id}/{node_id}: {bucket!r}"
            )

        changed = False
        normalized: Dict[str, ValidationCacheEntry] = {}
        for domain_key, payload in list(bucket.items()):
            try:
                normalized_domain = self._normalize_execution_domain(domain_key)
            except ValueError:
                normalized_domain = DEFAULT_EXECUTION_DOMAIN
                changed = True
            converted = self._coerce_validation_cache_entry(
                payload,
                world_id=world_id,
                node_id=node_id,
                execution_domain=normalized_domain,
            )
            if converted is None:
                changed = True
                continue
            if converted.execution_domain != normalized_domain:
                normalized_domain = converted.execution_domain
                changed = True
            if not isinstance(payload, ValidationCacheEntry) or converted is not payload:
                changed = True
            normalized[normalized_domain] = converted

        if changed:
            world_cache[node_id] = normalized
            return normalized
        return bucket

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
        node_cache = self._ensure_validation_cache_bucket(world_id, node_id)
        if not node_cache:
            return None
        domain = self._normalize_execution_domain(execution_domain)
        entry = node_cache.get(domain)
        if not entry:
            return None
        expected_key = self._compute_eval_key(
            node_id=node_id,
            world_id=world_id,
            execution_domain=domain,
            contract_id=contract_id,
            dataset_fingerprint=dataset_fingerprint,
            code_version=code_version,
            resource_policy=resource_policy,
        )
        if entry.eval_key != expected_key:
            node_cache.pop(domain, None)
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
        domain = self._normalize_execution_domain(execution_domain)
        eval_key = self._compute_eval_key(
            node_id=node_id,
            world_id=world_id,
            execution_domain=domain,
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
            execution_domain=domain,
            contract_id=contract_id,
            dataset_fingerprint=dataset_fingerprint,
            code_version=code_version,
            resource_policy=resource_policy,
            result=result,
            metrics=dict(metrics),
            timestamp=ts,
        )
        world_cache = self.validation_cache.setdefault(world_id, {})
        node_cache = self._ensure_validation_cache_bucket(world_id, node_id)
        node_cache[domain] = entry
        self.audit.setdefault(world_id, WorldAuditLog()).entries.append(
            {
                "event": "validation_cached",
                "node_id": node_id,
                "execution_domain": domain,
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
            node_cache = self._ensure_validation_cache_bucket(world_id, node_id)
            if not node_cache:
                return
            if execution_domain is None:
                cache.pop(node_id, None)
                scope = {"scope": "node", "node_id": node_id}
            else:
                domain = self._normalize_execution_domain(execution_domain)
                node_cache.pop(domain, None)
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
        
    def _normalize_execution_domain(self, execution_domain: str | None) -> str:
        if execution_domain is None:
            return DEFAULT_EXECUTION_DOMAIN
        candidate = str(execution_domain).strip().lower()
        if not candidate:
            return DEFAULT_EXECUTION_DOMAIN
        if candidate not in EXECUTION_DOMAINS:
            raise ValueError(f"unknown execution_domain: {execution_domain}")
        return candidate

    def _normalize_world_node_status(self, status: str | None) -> str:
        if status is None:
            return DEFAULT_WORLD_NODE_STATUS
        candidate = str(status).strip().lower()
        if not candidate:
            return DEFAULT_WORLD_NODE_STATUS
        if candidate not in WORLD_NODE_STATUSES:
            raise ValueError(f"unknown world node status: {status}")
        return candidate

    def _make_world_node_ref(
        self,
        world_id: str,
        node_id: str,
        execution_domain: str | None,
        status: str | None,
        last_eval_key: str | None,
        annotations: Any | None,
    ) -> Dict[str, Any]:
        normalized_domain = self._normalize_execution_domain(execution_domain)
        normalized_status = self._normalize_world_node_status(status)
        return {
            "world_id": world_id,
            "node_id": node_id,
            "execution_domain": normalized_domain,
            "status": normalized_status,
            "last_eval_key": last_eval_key,
            "annotations": deepcopy(annotations) if annotations is not None else None,
        }

    def _ensure_world_node_bucket(self, world_id: str, node_id: str) -> Dict[str, Dict[str, Any]]:
        bucket = self.world_nodes.setdefault(world_id, {})
        entry = bucket.get(node_id)
        if entry is None:
            entry = {}
            bucket[node_id] = entry
            return entry
        if isinstance(entry, dict) and "status" in entry:
            normalized = self._make_world_node_ref(
                world_id,
                node_id,
                entry.get("execution_domain"),
                entry.get("status"),
                entry.get("last_eval_key"),
                entry.get("annotations"),
            )
            converted: Dict[str, Dict[str, Any]] = {normalized["execution_domain"]: normalized}
            bucket[node_id] = converted
            return converted
        if isinstance(entry, dict):
            converted = {}
            for domain_key, node_data in list(entry.items()):
                if not isinstance(node_data, dict):
                    raise TypeError(f"unexpected world node payload for {world_id}/{node_id}: {node_data!r}")
                normalized = self._make_world_node_ref(
                    world_id,
                    node_id,
                    node_data.get("execution_domain", domain_key),
                    node_data.get("status"),
                    node_data.get("last_eval_key"),
                    node_data.get("annotations"),
                )
                converted[normalized["execution_domain"]] = normalized
            bucket[node_id] = converted
            return converted
        raise TypeError(f"unexpected world node container for {world_id}/{node_id}: {entry!r}")

    def _clone_world_node_ref(self, node: Dict[str, Any]) -> Dict[str, Any]:
        annotations = node.get("annotations")
        return {
            "world_id": node["world_id"],
            "node_id": node["node_id"],
            "execution_domain": node["execution_domain"],
            "status": node["status"],
            "last_eval_key": node.get("last_eval_key"),
            "annotations": deepcopy(annotations) if annotations is not None else None,
        }

    async def upsert_world_node(
        self,
        world_id: str,
        node_id: str,
        *,
        execution_domain: str | None = None,
        status: str | None = None,
        last_eval_key: str | None = None,
        annotations: Any | None = None,
    ) -> Dict[str, Any]:
        bucket = self._ensure_world_node_bucket(world_id, node_id)
        ref = self._make_world_node_ref(world_id, node_id, execution_domain, status, last_eval_key, annotations)
        bucket[ref["execution_domain"]] = ref
        self.audit.setdefault(world_id, WorldAuditLog()).entries.append(
            {
                "event": "world_node_upserted",
                "node_id": node_id,
                "execution_domain": ref["execution_domain"],
                "status": ref["status"],
            }
        )
        return self._clone_world_node_ref(ref)

    async def get_world_node(
        self,
        world_id: str,
        node_id: str,
        *,
        execution_domain: str | None = None,
    ) -> Optional[Dict[str, Any]]:
        nodes = self.world_nodes.get(world_id)
        if not nodes or node_id not in nodes:
            return None
        bucket = self._ensure_world_node_bucket(world_id, node_id)
        domain = self._normalize_execution_domain(execution_domain)
        ref = bucket.get(domain)
        if not ref:
            return None
        return self._clone_world_node_ref(ref)

    async def list_world_nodes(
        self,
        world_id: str,
        *,
        execution_domain: str | None = None,
    ) -> List[Dict[str, Any]]:
        nodes = self.world_nodes.get(world_id)
        if not nodes:
            return []
        include_all = False
        domain_filter: Optional[str]
        if execution_domain is None:
            domain_filter = self._normalize_execution_domain(None)
        else:
            candidate = str(execution_domain).strip().lower()
            if not candidate:
                domain_filter = self._normalize_execution_domain(None)
            elif candidate in {"*", "all"}:
                include_all = True
                domain_filter = None
            else:
                domain_filter = self._normalize_execution_domain(candidate)
        results: List[Dict[str, Any]] = []
        for node_id in sorted(nodes.keys()):
            bucket = self._ensure_world_node_bucket(world_id, node_id)
            if include_all:
                for domain in sorted(bucket.keys()):
                    results.append(self._clone_world_node_ref(bucket[domain]))
            else:
                if domain_filter is None:
                    continue
                ref = bucket.get(domain_filter)
                if ref:
                    results.append(self._clone_world_node_ref(ref))
        return results

    async def delete_world_node(
        self,
        world_id: str,
        node_id: str,
        *,
        execution_domain: str | None = None,
    ) -> None:
        nodes = self.world_nodes.get(world_id)
        if not nodes or node_id not in nodes:
            return
        bucket = self._ensure_world_node_bucket(world_id, node_id)
        domain = self._normalize_execution_domain(execution_domain)
        ref = bucket.pop(domain, None)
        if ref:
            if not bucket:
                nodes.pop(node_id, None)
            self.audit.setdefault(world_id, WorldAuditLog()).entries.append(
                {
                    "event": "world_node_deleted",
                    "node_id": node_id,
                    "execution_domain": domain,
                    "status": ref.get("status"),
                }
            )

    async def get_activation(self, world_id: str, strategy_id: str | None = None, side: str | None = None) -> Dict:
        act = self.activations.get(world_id)
        if not act:
            return {"version": 0, "state": {}}
        if strategy_id is not None and side is not None:
            data = act.state.get(strategy_id, {}).get(side, {})
            return {"version": act.version, **data}
        return {"version": act.version, "state": act.state}

    async def snapshot_activation(self, world_id: str) -> WorldActivation:
        act = self.activations.get(world_id)
        if not act:
            return WorldActivation()
        return WorldActivation(
            version=act.version,
            state={sid: {side: dict(val) for side, val in sides.items()} for sid, sides in act.state.items()},
        )

    async def restore_activation(self, world_id: str, snapshot: WorldActivation) -> None:
        self.activations[world_id] = WorldActivation(
            version=snapshot.version,
            state={sid: {side: dict(val) for side, val in sides.items()} for sid, sides in snapshot.state.items()},
        )

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

    async def record_apply_stage(self, world_id: str, run_id: str, stage: str, **details: object) -> None:
        entry = {
            "event": "apply_stage",
            "run_id": run_id,
            "stage": stage,
            "ts": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        }
        for key, val in details.items():
            if val is not None:
                entry[key] = val
        self.audit.setdefault(world_id, WorldAuditLog()).entries.append(entry)

    async def get_audit(self, world_id: str) -> List[Dict]:
        return list(self.audit.get(world_id, WorldAuditLog()).entries)

    async def upsert_edge_override(
        self,
        world_id: str,
        src_node_id: str,
        dst_node_id: str,
        *,
        active: bool,
        reason: str | None | object = _REASON_UNSET,
    ) -> Dict[str, Any]:
        bucket = self.edge_overrides.setdefault(world_id, {})
        key = (src_node_id, dst_node_id)
        previous = bucket.get(key)
        if reason is _REASON_UNSET:
            resolved_reason = previous.get("reason") if previous else None
        else:
            resolved_reason = None if reason is None else str(reason)
            if resolved_reason is not None:
                resolved_reason = resolved_reason.strip()
                if not resolved_reason:
                    resolved_reason = None

        ts = (
            datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )
        payload: Dict[str, Any] = {
            "src_node_id": src_node_id,
            "dst_node_id": dst_node_id,
            "active": bool(active),
            "updated_at": ts,
        }
        if resolved_reason is not None:
            payload["reason"] = resolved_reason

        bucket[key] = payload
        self.audit.setdefault(world_id, WorldAuditLog()).entries.append(
            {
                "event": "edge_override_upserted",
                "src_node_id": src_node_id,
                "dst_node_id": dst_node_id,
                "active": bool(active),
                "reason": resolved_reason,
                "updated_at": ts,
            }
        )
        return self._clone_edge_override(world_id, payload)

    async def get_edge_override(
        self, world_id: str, src_node_id: str, dst_node_id: str
    ) -> Optional[Dict[str, Any]]:
        bucket = self.edge_overrides.get(world_id)
        if not bucket:
            return None
        entry = bucket.get((src_node_id, dst_node_id))
        if not entry:
            return None
        return self._clone_edge_override(world_id, entry)

    async def list_edge_overrides(self, world_id: str) -> List[Dict[str, Any]]:
        bucket = self.edge_overrides.get(world_id)
        if not bucket:
            return []
        results: List[Dict[str, Any]] = []
        for src_node_id, dst_node_id in sorted(bucket.keys()):
            payload = bucket[(src_node_id, dst_node_id)]
            results.append(self._clone_edge_override(world_id, payload))
        return results

    async def delete_edge_override(
        self, world_id: str, src_node_id: str, dst_node_id: str
    ) -> None:
        bucket = self.edge_overrides.get(world_id)
        if not bucket:
            return
        entry = bucket.pop((src_node_id, dst_node_id), None)
        if entry is None:
            return
        if not bucket:
            self.edge_overrides.pop(world_id, None)
        self.audit.setdefault(world_id, WorldAuditLog()).entries.append(
            {
                "event": "edge_override_deleted",
                "src_node_id": src_node_id,
                "dst_node_id": dst_node_id,
                "active": entry.get("active"),
            }
        )

    async def _ensure_default_edge_overrides(self, world_id: str) -> None:
        for src_node_id, dst_node_id, reason in DEFAULT_EDGE_OVERRIDES:
            existing = await self.get_edge_override(world_id, src_node_id, dst_node_id)
            if existing is None:
                await self.upsert_edge_override(
                    world_id,
                    src_node_id,
                    dst_node_id,
                    active=False,
                    reason=reason,
                )

    def _clone_edge_override(self, world_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        data = {
            "world_id": world_id,
            "src_node_id": payload["src_node_id"],
            "dst_node_id": payload["dst_node_id"],
            "active": bool(payload.get("active", False)),
        }
        if "reason" in payload:
            data["reason"] = payload["reason"]
        if "updated_at" in payload:
            data["updated_at"] = payload["updated_at"]
        return data


__all__ = [
    'DEFAULT_EDGE_OVERRIDES',
    'DEFAULT_EXECUTION_DOMAIN',
    'DEFAULT_WORLD_NODE_STATUS',
    'EXECUTION_DOMAINS',
    'WORLD_NODE_STATUSES',
    'WorldActivation',
    'WorldPolicies',
    'WorldAuditLog',
    'ValidationCacheEntry',
    'Storage',
]
