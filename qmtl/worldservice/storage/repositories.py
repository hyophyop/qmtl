"""Domain-specific repositories backing the WorldService in-memory storage."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, MutableMapping, Optional

from qmtl.common.hashutils import hash_bytes

from .constants import (
    DEFAULT_EDGE_OVERRIDES,
    DEFAULT_EXECUTION_DOMAIN,
    DEFAULT_WORLD_NODE_STATUS,
    EXECUTION_DOMAINS,
    WORLD_NODE_STATUSES,
)
from .models import (
    ActivationEntry,
    ActivationState,
    EdgeOverrideRecord,
    PolicyVersion,
    ValidationCacheEntry,
    WorldActivation,
    WorldAuditLog,
    WorldNodeRef,
    WorldPolicies,
    WorldRecord,
)


def _normalize_execution_domain(execution_domain: str | None) -> str:
    if execution_domain is None:
        return DEFAULT_EXECUTION_DOMAIN
    candidate = str(execution_domain).strip().lower()
    if not candidate:
        return DEFAULT_EXECUTION_DOMAIN
    if candidate not in EXECUTION_DOMAINS:
        raise ValueError(f"unknown execution_domain: {execution_domain}")
    return candidate


def _normalize_world_node_status(status: str | None) -> str:
    if status is None:
        return DEFAULT_WORLD_NODE_STATUS
    candidate = str(status).strip().lower()
    if not candidate:
        return DEFAULT_WORLD_NODE_STATUS
    if candidate not in WORLD_NODE_STATUSES:
        raise ValueError(f"unknown world node status: {status}")
    return candidate


class AuditLogRepository:
    """Stores audit events per world."""

    def __init__(self) -> None:
        self.logs: Dict[str, WorldAuditLog] = {}

    def append(self, world_id: str, entry: Dict[str, Any]) -> None:
        self.logs.setdefault(world_id, WorldAuditLog()).entries.append(dict(entry))

    def get(self, world_id: str) -> WorldAuditLog:
        return self.logs.setdefault(world_id, WorldAuditLog())

    def list_entries(self, world_id: str) -> list[Dict[str, Any]]:
        return list(self.get(world_id).entries)

    def clear(self, world_id: str) -> None:
        self.logs.pop(world_id, None)


class WorldRepository:
    """CRUD around worlds."""

    def __init__(self, audit: AuditLogRepository) -> None:
        self._audit = audit
        self.records: Dict[str, WorldRecord] = {}

    def create(self, payload: Mapping[str, Any]) -> WorldRecord:
        record = WorldRecord.from_payload(payload)
        self.records[record.id] = record
        self._audit.append(record.id, {"event": "world_created", "world": record.to_dict()})
        return record

    def list(self) -> list[Dict[str, Any]]:
        return [record.to_dict() for record in self.records.values()]

    def get(self, world_id: str) -> Optional[Dict[str, Any]]:
        record = self.records.get(world_id)
        if record is None:
            return None
        return record.to_dict()

    def update(self, world_id: str, payload: Mapping[str, Any]) -> WorldRecord:
        if world_id not in self.records:
            raise KeyError(world_id)
        record = self.records[world_id]
        record.update(payload)
        self._audit.append(world_id, {"event": "world_updated", "world": record.to_dict()})
        return record

    def delete(self, world_id: str) -> None:
        self.records.pop(world_id, None)
        self._audit.append(world_id, {"event": "world_deleted"})


class PolicyRepository:
    """Manages policy revisions for a world."""

    def __init__(self, audit: AuditLogRepository) -> None:
        self._audit = audit
        self._policies: Dict[str, WorldPolicies] = {}

    def add(self, world_id: str, policy: Any) -> PolicyVersion:
        bundle = self._policies.setdefault(world_id, WorldPolicies())
        version = max(bundle.versions.keys(), default=0) + 1
        record = PolicyVersion(version=version, payload=policy)
        bundle.versions[version] = record
        if bundle.default is None:
            bundle.default = version
        self._audit.append(world_id, {"event": "policy_added", "version": version})
        return record

    def list_versions(self, world_id: str) -> list[Dict[str, int]]:
        bundle = self._policies.get(world_id)
        if not bundle:
            return []
        return [{"version": version} for version in sorted(bundle.versions.keys())]

    def get(self, world_id: str, version: int) -> Optional[Any]:
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
        self._audit.append(world_id, {"event": "policy_default_set", "version": version})

    def get_default(self, world_id: str) -> Optional[Any]:
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


class BindingRepository:
    """Stores strategy bindings."""

    def __init__(self, audit: AuditLogRepository) -> None:
        self._audit = audit
        self.bindings: Dict[str, set[str]] = {}

    def add(self, world_id: str, strategies: Iterable[str]) -> None:
        bucket = self.bindings.setdefault(world_id, set())
        sequence = list(strategies)
        bucket.update(sequence)
        self._audit.append(world_id, {"event": "bindings_added", "strategies": sequence})

    def list(self, world_id: str) -> list[str]:
        return sorted(self.bindings.get(world_id, set()))

    def clear(self, world_id: str) -> None:
        self.bindings.pop(world_id, None)


class DecisionRepository:
    """Maintains decision snapshots for a world."""

    def __init__(self, audit: AuditLogRepository) -> None:
        self._audit = audit
        self.decisions: Dict[str, list[str]] = {}

    def set(self, world_id: str, strategies: Iterable[str]) -> None:
        sequence = list(strategies)
        self.decisions[world_id] = sequence
        self._audit.append(world_id, {"event": "decisions_set", "strategies": sequence})

    def get(self, world_id: str) -> list[str]:
        return list(self.decisions.get(world_id, []))

    def clear(self, world_id: str) -> None:
        self.decisions.pop(world_id, None)


class ActivationRepository:
    """Tracks activation state per world."""

    def __init__(self, audit: AuditLogRepository) -> None:
        self._audit = audit
        self.activations: Dict[str, ActivationState] = {}

    def get(self, world_id: str, strategy_id: str | None = None, side: str | None = None) -> Dict[str, Any]:
        record = self.activations.get(world_id)
        if not record:
            return {"version": 0, "state": {}}
        if strategy_id is not None and side is not None:
            entry = record.state.get(strategy_id, {}).get(side)
            payload: Dict[str, Any] = {"version": record.version}
            if entry:
                payload.update(entry.to_dict())
            return payload
        snapshot = WorldActivation.from_internal(record)
        return {"version": snapshot.version, "state": snapshot.state}

    def snapshot(self, world_id: str) -> WorldActivation:
        record = self.activations.get(world_id)
        if not record:
            return WorldActivation()
        return WorldActivation.from_internal(record.clone())

    def restore(self, world_id: str, snapshot: WorldActivation) -> None:
        self.activations[world_id] = snapshot.to_internal()

    def update(self, world_id: str, payload: Mapping[str, Any]) -> tuple[int, Dict[str, Any]]:
        record = self.activations.setdefault(world_id, ActivationState())
        record.version += 1
        strategy_id = str(payload["strategy_id"])
        side = str(payload["side"])
        ts = payload.get("ts") or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        etag = f"act:{world_id}:{strategy_id}:{side}:{record.version}"
        entry = ActivationEntry(
            active=bool(payload.get("active", False)),
            weight=float(payload.get("weight", 1.0)),
            freeze=bool(payload.get("freeze", False)),
            drain=bool(payload.get("drain", False)),
            effective_mode=payload.get("effective_mode"),
            run_id=payload.get("run_id"),
            ts=ts,
            etag=etag,
        )
        record.state.setdefault(strategy_id, {})[side] = entry
        audit_payload = {"event": "activation_updated", "version": record.version, "strategy_id": strategy_id, "side": side}
        audit_payload.update(entry.to_dict())
        self._audit.append(world_id, audit_payload)
        return record.version, entry.to_dict()

    def clear(self, world_id: str) -> None:
        self.activations.pop(world_id, None)


class WorldNodeRepository:
    """Maintains node/domain references per world."""

    def __init__(self, audit: AuditLogRepository) -> None:
        self._audit = audit
        self.nodes: Dict[str, Dict[str, Dict[str, WorldNodeRef]]] = {}

    def _make_ref(
        self,
        world_id: str,
        node_id: str,
        execution_domain: str | None,
        status: str | None,
        last_eval_key: str | None,
        annotations: Any | None,
    ) -> WorldNodeRef:
        domain = _normalize_execution_domain(execution_domain)
        resolved_status = _normalize_world_node_status(status)
        return WorldNodeRef(
            world_id=world_id,
            node_id=node_id,
            execution_domain=domain,
            status=resolved_status,
            last_eval_key=last_eval_key,
            annotations=deepcopy(annotations) if annotations is not None else None,
        )

    def _ensure_bucket(self, world_id: str, node_id: str) -> Dict[str, WorldNodeRef]:
        world_bucket = self.nodes.setdefault(world_id, {})
        bucket = world_bucket.get(node_id)
        if bucket is None:
            bucket = {}
            world_bucket[node_id] = bucket
            return bucket
        if isinstance(bucket, dict) and bucket and isinstance(next(iter(bucket.values())), WorldNodeRef):
            return bucket
        if isinstance(bucket, dict) and "status" in bucket:
            ref = self._make_ref(
                world_id,
                node_id,
                bucket.get("execution_domain"),
                bucket.get("status"),
                bucket.get("last_eval_key"),
                bucket.get("annotations"),
            )
            container = {ref.execution_domain: ref}
            world_bucket[node_id] = container
            self._audit.append(
                world_id,
                {
                    "event": "world_node_bucket_normalized",
                    "node_id": node_id,
                    "domains": [ref.execution_domain],
                    "source": "legacy-single",
                },
            )
            return container
        if isinstance(bucket, dict):
            container: Dict[str, WorldNodeRef] = {}
            changed = False
            updated_domains: set[str] = set()
            dropped_domains: set[str] = set()
            for domain_key, payload in list(bucket.items()):
                if isinstance(payload, WorldNodeRef):
                    ref = payload
                    domain = ref.execution_domain
                elif isinstance(payload, Mapping):
                    ref = self._make_ref(
                        world_id,
                        node_id,
                        payload.get("execution_domain", domain_key),
                        payload.get("status"),
                        payload.get("last_eval_key"),
                        payload.get("annotations"),
                    )
                    domain = ref.execution_domain
                else:
                    raise TypeError(f"unexpected world node payload for {world_id}/{node_id}: {payload!r}")
                if domain_key != domain or container.get(domain) is not ref:
                    changed = True
                    updated_domains.add(domain)
                if domain in container:
                    changed = True
                    dropped_domains.add(str(domain_key))
                container[domain] = ref if isinstance(payload, WorldNodeRef) else ref
            if changed:
                world_bucket[node_id] = container
                audit_payload: Dict[str, Any] = {
                    "event": "world_node_bucket_normalized",
                    "node_id": node_id,
                    "domains": sorted(container.keys()),
                    "source": "bucket",
                }
                if updated_domains:
                    audit_payload["updated_domains"] = sorted(updated_domains)
                if dropped_domains:
                    audit_payload["dropped_domains"] = sorted(dropped_domains)
                self._audit.append(world_id, audit_payload)
                return container
            return bucket  # type: ignore[return-value]
        raise TypeError(f"unexpected world node container for {world_id}/{node_id}: {bucket!r}")

    def upsert(
        self,
        world_id: str,
        node_id: str,
        *,
        execution_domain: str | None = None,
        status: str | None = None,
        last_eval_key: str | None = None,
        annotations: Any | None = None,
    ) -> Dict[str, Any]:
        bucket = self._ensure_bucket(world_id, node_id)
        ref = self._make_ref(world_id, node_id, execution_domain, status, last_eval_key, annotations)
        bucket[ref.execution_domain] = ref
        self._audit.append(
            world_id,
            {
                "event": "world_node_upserted",
                "node_id": node_id,
                "execution_domain": ref.execution_domain,
                "status": ref.status,
            },
        )
        return ref.clone().to_dict()

    def get(
        self,
        world_id: str,
        node_id: str,
        *,
        execution_domain: str | None = None,
    ) -> Optional[Dict[str, Any]]:
        world_bucket = self.nodes.get(world_id)
        if not world_bucket or node_id not in world_bucket:
            return None
        bucket = self._ensure_bucket(world_id, node_id)
        domain = _normalize_execution_domain(execution_domain)
        ref = bucket.get(domain)
        if not ref:
            return None
        return ref.clone().to_dict()

    def list(
        self,
        world_id: str,
        *,
        execution_domain: str | None = None,
    ) -> list[Dict[str, Any]]:
        world_bucket = self.nodes.get(world_id)
        if not world_bucket:
            return []
        include_all = False
        domain_filter: Optional[str]
        if execution_domain is None:
            domain_filter = _normalize_execution_domain(None)
        else:
            candidate = str(execution_domain).strip().lower()
            if not candidate:
                domain_filter = _normalize_execution_domain(None)
            elif candidate in {"*", "all"}:
                include_all = True
                domain_filter = None
            else:
                domain_filter = _normalize_execution_domain(candidate)
        results: list[Dict[str, Any]] = []
        for node_id in sorted(world_bucket.keys()):
            bucket = self._ensure_bucket(world_id, node_id)
            if include_all:
                for domain in sorted(bucket.keys()):
                    results.append(bucket[domain].clone().to_dict())
            else:
                if domain_filter is None:
                    continue
                ref = bucket.get(domain_filter)
                if ref:
                    results.append(ref.clone().to_dict())
        return results

    def delete(
        self,
        world_id: str,
        node_id: str,
        *,
        execution_domain: str | None = None,
    ) -> None:
        world_bucket = self.nodes.get(world_id)
        if not world_bucket or node_id not in world_bucket:
            return
        bucket = self._ensure_bucket(world_id, node_id)
        domain = _normalize_execution_domain(execution_domain)
        ref = bucket.pop(domain, None)
        if ref:
            if not bucket:
                world_bucket.pop(node_id, None)
            self._audit.append(
                world_id,
                {
                    "event": "world_node_deleted",
                    "node_id": node_id,
                    "execution_domain": domain,
                    "status": ref.status,
                },
            )

    def clear(self, world_id: str) -> None:
        self.nodes.pop(world_id, None)


class ValidationCacheRepository:
    """Caches validation responses keyed by execution domain."""

    def __init__(self, audit: AuditLogRepository) -> None:
        self._audit = audit
        self.cache: Dict[str, Dict[str, Dict[str, ValidationCacheEntry]]] = {}

    @staticmethod
    def _compute_eval_key(
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

    def _coerce_entry(
        self,
        entry: ValidationCacheEntry | Mapping[str, Any],
        *,
        world_id: str,
        node_id: str,
        execution_domain: str,
    ) -> Optional[ValidationCacheEntry]:
        if isinstance(entry, ValidationCacheEntry):
            normalized_domain = _normalize_execution_domain(entry.execution_domain)
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

        if not isinstance(entry, Mapping):
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

        if not all(isinstance(val, str) for val in (eval_key, contract_id, dataset_fingerprint, code_version, resource_policy, result, timestamp)):
            return None

        metrics = entry.get("metrics") or {}
        if not isinstance(metrics, MutableMapping):
            metrics = dict(metrics)

        node_value = entry.get("node_id")
        node_value = node_value if isinstance(node_value, str) else node_id

        domain_value = entry.get("execution_domain", execution_domain)
        try:
            normalized_domain = _normalize_execution_domain(domain_value)
        except ValueError:
            normalized_domain = DEFAULT_EXECUTION_DOMAIN

        return ValidationCacheEntry(
            eval_key=str(eval_key),
            node_id=node_value,
            execution_domain=normalized_domain,
            contract_id=str(contract_id),
            dataset_fingerprint=str(dataset_fingerprint),
            code_version=str(code_version),
            resource_policy=str(resource_policy),
            result=str(result),
            metrics=dict(metrics),
            timestamp=str(timestamp),
        )

    def _ensure_bucket(self, world_id: str, node_id: str) -> Dict[str, ValidationCacheEntry]:
        world_bucket = self.cache.setdefault(world_id, {})
        bucket = world_bucket.get(node_id)
        if bucket is None:
            bucket = {}
            world_bucket[node_id] = bucket
            return bucket
        if not isinstance(bucket, dict):
            raise TypeError(f"unexpected validation cache container for {world_id}/{node_id}: {bucket!r}")
        changed = False
        normalized: Dict[str, ValidationCacheEntry] = {}
        updated_domains: set[str] = set()
        dropped_domains: set[str] = set()
        for domain_key, payload in list(bucket.items()):
            try:
                normalized_domain = _normalize_execution_domain(domain_key)
            except ValueError:
                normalized_domain = DEFAULT_EXECUTION_DOMAIN
                changed = True
                updated_domains.add(normalized_domain)
            converted = self._coerce_entry(
                payload,
                world_id=world_id,
                node_id=node_id,
                execution_domain=normalized_domain,
            )
            if converted is None:
                changed = True
                dropped_domains.add(str(domain_key))
                continue
            if converted.execution_domain != normalized_domain:
                normalized_domain = converted.execution_domain
                changed = True
                updated_domains.add(normalized_domain)
            if not isinstance(payload, ValidationCacheEntry) or converted is not payload:
                changed = True
                updated_domains.add(normalized_domain)
            if normalized_domain in normalized:
                changed = True
                dropped_domains.add(str(domain_key))
            normalized[normalized_domain] = converted
        if changed:
            world_bucket[node_id] = normalized
            audit_payload: Dict[str, Any] = {
                "event": "validation_cache_bucket_normalized",
                "node_id": node_id,
                "domains": sorted(normalized.keys()),
            }
            if updated_domains:
                audit_payload["updated_domains"] = sorted(updated_domains)
            if dropped_domains:
                audit_payload["dropped_domains"] = sorted(dropped_domains)
            self._audit.append(world_id, audit_payload)
            return normalized
        return bucket

    def get(
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
        world_bucket = self.cache.get(world_id)
        if not world_bucket:
            return None
        node_bucket = self._ensure_bucket(world_id, node_id)
        if not node_bucket:
            return None
        domain = _normalize_execution_domain(execution_domain)
        entry = node_bucket.get(domain)
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
            node_bucket.pop(domain, None)
            if not node_bucket:
                world_bucket.pop(node_id, None)
            if not world_bucket:
                self.cache.pop(world_id, None)
            self._audit.append(
                world_id,
                {
                    "event": "validation_cache_invalidated",
                    "reason": "context_mismatch",
                    "node_id": node_id,
                    "execution_domain": execution_domain,
                    "stored_eval_key": entry.eval_key,
                    "expected_eval_key": expected_key,
                },
            )
            return None
        return entry

    def set(
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
        metrics: Mapping[str, Any],
        timestamp: str | None = None,
    ) -> ValidationCacheEntry:
        domain = _normalize_execution_domain(execution_domain)
        eval_key = self._compute_eval_key(
            node_id=node_id,
            world_id=world_id,
            execution_domain=domain,
            contract_id=contract_id,
            dataset_fingerprint=dataset_fingerprint,
            code_version=code_version,
            resource_policy=resource_policy,
        )
        ts = timestamp or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
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
        world_bucket = self.cache.setdefault(world_id, {})
        node_bucket = self._ensure_bucket(world_id, node_id)
        node_bucket[domain] = entry
        self._audit.append(
            world_id,
            {
                "event": "validation_cached",
                "node_id": node_id,
                "execution_domain": domain,
                "eval_key": eval_key,
            },
        )
        return entry

    def invalidate(
        self,
        world_id: str,
        *,
        node_id: str | None = None,
        execution_domain: str | None = None,
    ) -> None:
        world_bucket = self.cache.get(world_id)
        if not world_bucket:
            return
        if node_id is None:
            self.cache.pop(world_id, None)
            scope: Dict[str, Any] = {"scope": "world"}
        else:
            node_bucket = self._ensure_bucket(world_id, node_id)
            if not node_bucket:
                return
            if execution_domain is None:
                world_bucket.pop(node_id, None)
                scope = {"scope": "node", "node_id": node_id}
            else:
                domain = _normalize_execution_domain(execution_domain)
                node_bucket.pop(domain, None)
                if not node_bucket:
                    world_bucket.pop(node_id, None)
                scope = {"scope": "domain", "node_id": node_id, "execution_domain": execution_domain}
            if not world_bucket:
                self.cache.pop(world_id, None)
        self._audit.append(world_id, {"event": "validation_cache_cleared", **scope})

    def clear(self, world_id: str) -> None:
        self.cache.pop(world_id, None)


class EdgeOverrideRepository:
    """Stores edge override state."""

    def __init__(self, audit: AuditLogRepository) -> None:
        self._audit = audit
        self.overrides: Dict[str, Dict[tuple[str, str], EdgeOverrideRecord]] = {}

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    def upsert(
        self,
        world_id: str,
        src_node_id: str,
        dst_node_id: str,
        *,
        active: bool,
        reason: str | None | object,
    ) -> EdgeOverrideRecord:
        bucket = self.overrides.setdefault(world_id, {})
        key = (src_node_id, dst_node_id)
        previous = bucket.get(key)
        if reason is _REASON_UNSET:
            resolved_reason = previous.reason if previous else None
        else:
            resolved_reason = None if reason is None else str(reason).strip() or None
        record = EdgeOverrideRecord(
            src_node_id=src_node_id,
            dst_node_id=dst_node_id,
            active=bool(active),
            updated_at=self._now(),
            reason=resolved_reason,
        )
        bucket[key] = record
        self._audit.append(
            world_id,
            {
                "event": "edge_override_upserted",
                "src_node_id": src_node_id,
                "dst_node_id": dst_node_id,
                "active": bool(active),
                "reason": resolved_reason,
                "updated_at": record.updated_at,
            },
        )
        return record

    def get(self, world_id: str, src_node_id: str, dst_node_id: str) -> Optional[EdgeOverrideRecord]:
        bucket = self.overrides.get(world_id)
        if not bucket:
            return None
        record = bucket.get((src_node_id, dst_node_id))
        return None if record is None else record.clone()

    def list(self, world_id: str) -> list[EdgeOverrideRecord]:
        bucket = self.overrides.get(world_id)
        if not bucket:
            return []
        return [payload.clone() for payload in (bucket[key] for key in sorted(bucket.keys()))]

    def delete(self, world_id: str, src_node_id: str, dst_node_id: str) -> None:
        bucket = self.overrides.get(world_id)
        if not bucket:
            return
        record = bucket.pop((src_node_id, dst_node_id), None)
        if record is None:
            return
        if not bucket:
            self.overrides.pop(world_id, None)
        self._audit.append(
            world_id,
            {
                "event": "edge_override_deleted",
                "src_node_id": src_node_id,
                "dst_node_id": dst_node_id,
                "active": record.active,
            },
        )

    async def ensure_defaults(self, world_id: str) -> None:
        for src_node_id, dst_node_id, reason in DEFAULT_EDGE_OVERRIDES:
            existing = self.get(world_id, src_node_id, dst_node_id)
            if existing is None:
                self.upsert(world_id, src_node_id, dst_node_id, active=False, reason=reason)

    def clear(self, world_id: str) -> None:
        self.overrides.pop(world_id, None)


# Sentinel reused by the facade for compatibility with legacy behaviour.
_REASON_UNSET = object()


__all__ = [
    "ActivationRepository",
    "AuditLogRepository",
    "BindingRepository",
    "DecisionRepository",
    "EdgeOverrideRepository",
    "PolicyRepository",
    "ValidationCacheRepository",
    "WorldNodeRepository",
    "WorldRepository",
    "_REASON_UNSET",
]
