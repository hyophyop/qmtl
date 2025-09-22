"""Facade that composes domain repositories to emulate the legacy Storage API."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from .models import ValidationCacheEntry, WorldActivation, WorldAuditLog
from .repositories import (
    ActivationRepository,
    AuditLogRepository,
    BindingRepository,
    DecisionRepository,
    EdgeOverrideRepository,
    PolicyRepository,
    ValidationCacheRepository,
    WorldNodeRepository,
    WorldRepository,
    _REASON_UNSET,
    _normalize_execution_domain,
)
from qmtl.worldservice.policy_engine import Policy


class Storage:
    """In-memory storage backing WorldService endpoints."""

    def __init__(self) -> None:
        self._audit = AuditLogRepository()
        self._worlds = WorldRepository(self._audit)
        self._policies = PolicyRepository(self._audit)
        self._bindings = BindingRepository(self._audit)
        self._decisions = DecisionRepository(self._audit)
        self._activations = ActivationRepository(self._audit)
        self._world_nodes = WorldNodeRepository(self._audit)
        self._validation_cache = ValidationCacheRepository(self._audit)
        self._edge_overrides = EdgeOverrideRepository(self._audit)

        # Compatibility accessors for legacy tests that inspect the raw state.
        self.audit: Dict[str, WorldAuditLog] = self._audit.logs
        self.validation_cache: Dict[str, Dict[str, Dict[str, ValidationCacheEntry]]] = (
            self._validation_cache.cache
        )
        self.world_nodes = self._world_nodes.nodes
        self.apply_runs: Dict[str, Dict[str, Any]] = {}

    async def create_world(self, world: Dict[str, Any]) -> None:
        record = self._worlds.create(world)
        await self._edge_overrides.ensure_defaults(record.id)

    async def list_worlds(self) -> List[Dict[str, Any]]:
        return self._worlds.list()

    async def get_world(self, world_id: str) -> Optional[Dict[str, Any]]:
        return self._worlds.get(world_id)

    async def update_world(self, world_id: str, data: Dict[str, Any]) -> None:
        self._worlds.update(world_id, data)
        if {"contract_id", "dataset_fingerprint", "resource_policy", "code_version"} & data.keys():
            await self.invalidate_validation_cache(world_id)

    async def delete_world(self, world_id: str) -> None:
        self._worlds.delete(world_id)
        self._activations.clear(world_id)
        self._policies.clear(world_id)
        self._bindings.clear(world_id)
        self._decisions.clear(world_id)
        self._world_nodes.clear(world_id)
        self._validation_cache.clear(world_id)
        self._edge_overrides.clear(world_id)

    async def add_policy(self, world_id: str, policy: Policy) -> int:
        record = self._policies.add(world_id, policy)
        await self.invalidate_validation_cache(world_id)
        return record.version

    async def list_policies(self, world_id: str) -> List[Dict[str, int]]:
        return self._policies.list_versions(world_id)

    async def get_policy(self, world_id: str, version: int) -> Optional[Policy]:
        return self._policies.get(world_id, version)

    async def set_default_policy(self, world_id: str, version: int) -> None:
        self._policies.set_default(world_id, version)
        await self.invalidate_validation_cache(world_id)

    async def get_default_policy(self, world_id: str) -> Optional[Policy]:
        return self._policies.get_default(world_id)

    async def default_policy_version(self, world_id: str) -> int:
        return self._policies.default_version(world_id)

    async def add_bindings(self, world_id: str, strategies: Iterable[str]) -> None:
        self._bindings.add(world_id, strategies)

    async def list_bindings(self, world_id: str) -> List[str]:
        return self._bindings.list(world_id)

    async def set_decisions(self, world_id: str, strategies: List[str]) -> None:
        self._decisions.set(world_id, strategies)

    async def get_decisions(self, world_id: str) -> List[str]:
        return self._decisions.get(world_id)

    async def get_activation(
        self, world_id: str, strategy_id: str | None = None, side: str | None = None
    ) -> Dict[str, Any]:
        return self._activations.get(world_id, strategy_id=strategy_id, side=side)

    async def snapshot_activation(self, world_id: str) -> WorldActivation:
        return self._activations.snapshot(world_id)

    async def restore_activation(self, world_id: str, snapshot: WorldActivation) -> None:
        self._activations.restore(world_id, snapshot)

    async def update_activation(self, world_id: str, payload: Dict[str, Any]) -> tuple[int, Dict[str, Any]]:
        return self._activations.update(world_id, payload)

    async def record_apply_stage(self, world_id: str, run_id: str, stage: str, **details: Any) -> None:
        entry: Dict[str, Any] = {
            "event": "apply_stage",
            "run_id": run_id,
            "stage": stage,
            "ts": datetime_now(),
        }
        for key, value in details.items():
            if value is not None:
                entry[key] = value
        self._audit.append(world_id, entry)

    async def get_audit(self, world_id: str) -> List[Dict[str, Any]]:
        return self._audit.list_entries(world_id)

    async def upsert_edge_override(
        self,
        world_id: str,
        src_node_id: str,
        dst_node_id: str,
        *,
        active: bool,
        reason: str | None | object = _REASON_UNSET,
    ) -> Dict[str, Any]:
        record = self._edge_overrides.upsert(
            world_id,
            src_node_id,
            dst_node_id,
            active=active,
            reason=reason,
        )
        return record.to_dict(world_id)

    async def get_edge_override(
        self, world_id: str, src_node_id: str, dst_node_id: str
    ) -> Optional[Dict[str, Any]]:
        record = self._edge_overrides.get(world_id, src_node_id, dst_node_id)
        return None if record is None else record.to_dict(world_id)

    async def list_edge_overrides(self, world_id: str) -> List[Dict[str, Any]]:
        return [record.to_dict(world_id) for record in self._edge_overrides.list(world_id)]

    async def delete_edge_override(self, world_id: str, src_node_id: str, dst_node_id: str) -> None:
        self._edge_overrides.delete(world_id, src_node_id, dst_node_id)

    async def _ensure_default_edge_overrides(self, world_id: str) -> None:
        await self._edge_overrides.ensure_defaults(world_id)

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
        return self._validation_cache.get(
            world_id,
            node_id=node_id,
            execution_domain=execution_domain,
            contract_id=contract_id,
            dataset_fingerprint=dataset_fingerprint,
            code_version=code_version,
            resource_policy=resource_policy,
        )

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
        return self._validation_cache.set(
            world_id,
            node_id=node_id,
            execution_domain=execution_domain,
            contract_id=contract_id,
            dataset_fingerprint=dataset_fingerprint,
            code_version=code_version,
            resource_policy=resource_policy,
            result=result,
            metrics=metrics,
            timestamp=timestamp,
        )

    async def invalidate_validation_cache(
        self,
        world_id: str,
        *,
        node_id: str | None = None,
        execution_domain: str | None = None,
    ) -> None:
        self._validation_cache.invalidate(
            world_id,
            node_id=node_id,
            execution_domain=execution_domain,
        )

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
        return self._world_nodes.upsert(
            world_id,
            node_id,
            execution_domain=execution_domain,
            status=status,
            last_eval_key=last_eval_key,
            annotations=annotations,
        )

    async def get_world_node(
        self,
        world_id: str,
        node_id: str,
        *,
        execution_domain: str | None = None,
    ) -> Optional[Dict[str, Any]]:
        return self._world_nodes.get(world_id, node_id, execution_domain=execution_domain)

    async def list_world_nodes(
        self,
        world_id: str,
        *,
        execution_domain: str | None = None,
    ) -> List[Dict[str, Any]]:
        return self._world_nodes.list(world_id, execution_domain=execution_domain)

    async def delete_world_node(
        self,
        world_id: str,
        node_id: str,
        *,
        execution_domain: str | None = None,
    ) -> None:
        self._world_nodes.delete(world_id, node_id, execution_domain=execution_domain)

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
        """Backwards-compatible helper for tests touching the legacy API."""

        normalized_domain = _normalize_execution_domain(execution_domain)
        return self._validation_cache._compute_eval_key(  # type: ignore[attr-defined]
            node_id=node_id,
            world_id=world_id,
            execution_domain=normalized_domain,
            contract_id=contract_id,
            dataset_fingerprint=dataset_fingerprint,
            code_version=code_version,
            resource_policy=resource_policy,
        )


def datetime_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


__all__ = ["Storage"]
