"""Repository managing world node references."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any, Dict, Optional

from .auditable import AuditableRepository, AuditSink
from .models import WorldNodeRef
from .normalization import _normalize_execution_domain, _normalize_world_node_status


class WorldNodeRepository(AuditableRepository):
    """Maintains node/domain references per world."""

    def __init__(self, audit: AuditSink) -> None:
        super().__init__(audit)
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
            return self._normalize_legacy_single_bucket(world_id, node_id, world_bucket, bucket)
        if isinstance(bucket, dict):
            return self._normalize_bucket(world_id, node_id, world_bucket, bucket)
        raise TypeError(f"unexpected world node container for {world_id}/{node_id}: {bucket!r}")

    def _normalize_legacy_single_bucket(
        self,
        world_id: str,
        node_id: str,
        world_bucket: Dict[str, Dict[str, WorldNodeRef]],
        bucket: Dict[str, Any],
    ) -> Dict[str, WorldNodeRef]:
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
        self._emit_audit(
            world_id,
            {
                "event": "world_node_bucket_normalized",
                "node_id": node_id,
                "domains": [ref.execution_domain],
                "source": "legacy-single",
            },
        )
        return container

    def _normalize_bucket(
        self,
        world_id: str,
        node_id: str,
        world_bucket: Dict[str, Dict[str, WorldNodeRef]],
        bucket: Dict[str, Any],
    ) -> Dict[str, WorldNodeRef]:
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
            self._emit_audit(world_id, audit_payload)
            return container
        return bucket

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
        self._emit_audit(
            world_id,
            {
                "event": "world_node_upserted",
                "node_id": node_id,
                "execution_domain": ref.execution_domain,
                "status": ref.status,
            },
        )
        payload: Dict[str, Any] = ref.to_dict()
        return payload

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
        payload: Dict[str, Any] = ref.to_dict()
        return payload

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
                    results.append(bucket[domain].to_dict())
            else:
                if domain_filter is None:
                    continue
                ref = bucket.get(domain_filter)
                if ref:
                    results.append(ref.to_dict())
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
        bucket.pop(domain, None)
        if not bucket:
            world_bucket.pop(node_id, None)
        if not world_bucket:
            self.nodes.pop(world_id, None)
        self._emit_audit(
            world_id,
            {
                "event": "world_node_deleted",
                "node_id": node_id,
                "execution_domain": domain,
            },
        )

    def clear(self, world_id: str) -> None:
        self.nodes.pop(world_id, None)


__all__ = ["WorldNodeRepository"]
