"""Repository caching validation results."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any, Dict, MutableMapping, Optional

from qmtl.foundation.common.hashutils import hash_bytes

from .auditable import AuditableRepository, AuditSink
from .constants import DEFAULT_EXECUTION_DOMAIN
from .models import ValidationCacheEntry
from .normalization import _normalize_execution_domain


class ValidationCacheRepository(AuditableRepository):
    """Stores validation cache entries per world."""

    def __init__(self, audit: AuditSink) -> None:
        super().__init__(audit)
        self.cache: Dict[str, Dict[str, Dict[str, ValidationCacheEntry]]] = {}

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
        return hash_bytes(
            "\u0000".join(
                [
                    "validation-cache",
                    world_id,
                    node_id,
                    execution_domain,
                    contract_id,
                    dataset_fingerprint,
                    code_version,
                    resource_policy,
                ]
            ).encode("utf-8")
        )

    def _coerce_entry(
        self,
        entry: Any,
        *,
        world_id: str,
        node_id: str,
        execution_domain: str,
    ) -> ValidationCacheEntry | None:
        if isinstance(entry, ValidationCacheEntry):
            return ValidationCacheEntry(
                eval_key=entry.eval_key,
                node_id=entry.node_id,
                execution_domain=_normalize_execution_domain(entry.execution_domain),
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

        if not all(
            isinstance(val, str)
            for val in (
                eval_key,
                contract_id,
                dataset_fingerprint,
                code_version,
                resource_policy,
                result,
                timestamp,
            )
        ):
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
        if self._is_normalized_bucket(bucket):
            return bucket
        if isinstance(bucket, dict):
            normalized = self._normalize_bucket(world_id, node_id, bucket)
            world_bucket[node_id] = normalized
            return normalized
        raise TypeError(f"unexpected validation cache container for {world_id}/{node_id}: {bucket!r}")

    def _is_normalized_bucket(self, bucket: Any) -> bool:
        if not isinstance(bucket, dict):
            return False
        if not bucket:
            return True
        return all(isinstance(v, ValidationCacheEntry) for v in bucket.values())

    def _normalize_bucket(
        self, world_id: str, node_id: str, bucket: Dict[str, Any]
    ) -> Dict[str, ValidationCacheEntry]:
        changed = False
        normalized: Dict[str, ValidationCacheEntry] = {}
        updated_domains: set[str] = set()
        dropped_domains: set[str] = set()
        for domain_key, payload in list(bucket.items()):
            normalized_domain, converted, entry_changed, updated, dropped = self._normalize_entry(
                domain_key, payload, world_id, node_id
            )
            changed = changed or entry_changed
            updated_domains.update(updated)
            if dropped:
                dropped_domains.add(str(domain_key))
                continue
            if normalized_domain in normalized:
                changed = True
                dropped_domains.add(str(domain_key))
                continue
            normalized[normalized_domain] = converted
        if changed:
            audit_payload: Dict[str, Any] = {
                "event": "validation_cache_bucket_normalized",
                "node_id": node_id,
                "domains": sorted(normalized.keys()),
            }
            if updated_domains:
                audit_payload["updated_domains"] = sorted(updated_domains)
            if dropped_domains:
                audit_payload["dropped_domains"] = sorted(dropped_domains)
            self._emit_audit(world_id, audit_payload)
            return normalized
        return bucket

    def _normalize_entry(
        self,
        domain_key: str,
        payload: Any,
        world_id: str,
        node_id: str,
    ) -> tuple[str, ValidationCacheEntry | None, bool, set[str], bool]:
        entry_changed = False
        updated_domains: set[str] = set()
        try:
            normalized_domain = _normalize_execution_domain(domain_key)
        except ValueError:
            normalized_domain = DEFAULT_EXECUTION_DOMAIN
            entry_changed = True
            updated_domains.add(normalized_domain)
        converted = self._coerce_entry(
            payload,
            world_id=world_id,
            node_id=node_id,
            execution_domain=normalized_domain,
        )
        if converted is None:
            return normalized_domain, None, True, updated_domains, True
        if converted.execution_domain != normalized_domain:
            normalized_domain = converted.execution_domain
            entry_changed = True
            updated_domains.add(normalized_domain)
        if not isinstance(payload, ValidationCacheEntry) or converted is not payload:
            entry_changed = True
            updated_domains.add(normalized_domain)
        return normalized_domain, converted, entry_changed, updated_domains, False

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
            self._emit_audit(
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
        self._emit_audit(
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
        self._emit_audit(world_id, {"event": "validation_cache_cleared", **scope})

    def clear(self, world_id: str) -> None:
        self.cache.pop(world_id, None)


__all__ = ["ValidationCacheRepository"]
