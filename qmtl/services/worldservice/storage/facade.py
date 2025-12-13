"""Facade that composes domain repositories to emulate the legacy Storage API."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from .models import (
    AllocationRun,
    AllocationState,
    EvaluationRunRecord,
    ValidationCacheEntry,
    WorldActivation,
    WorldAuditLog,
)
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
from qmtl.services.worldservice.policy_engine import Policy


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
        self._world_allocations: Dict[str, AllocationState] = {}
        self._allocation_runs: Dict[str, AllocationRun] = {}
        self._evaluation_runs: Dict[tuple[str, str, str], EvaluationRunRecord] = {}
        self._evaluation_run_history: Dict[
            tuple[str, str, str], List[Dict[str, Any]]
        ] = {}
        self._history_metadata: Dict[str, Dict[str, Dict[str, Any]]] = {}

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
        self._history_metadata.pop(world_id, None)
        for key in list(self._evaluation_run_history.keys()):
            if key[0] == world_id:
                self._evaluation_run_history.pop(key, None)

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
        self._worlds.update(world_id, {"default_policy_version": version})
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

    async def upsert_history_metadata(
        self,
        world_id: str,
        strategy_id: str,
        payload: Dict[str, Any],
    ) -> None:
        bucket = self._history_metadata.setdefault(world_id, {})
        record = dict(payload)
        record["strategy_id"] = strategy_id
        bucket[strategy_id] = record
        self._audit.append(
            world_id,
            {
                "event": "history_metadata_upserted",
                "strategy_id": strategy_id,
                "dataset_fingerprint": record.get("dataset_fingerprint"),
                "as_of": record.get("as_of"),
                "updated_at": record.get("updated_at"),
            },
        )

    async def list_history_metadata(self, world_id: str) -> List[Dict[str, Any]]:
        bucket = self._history_metadata.get(world_id, {})
        return [dict(value) for _, value in sorted(bucket.items())]

    async def latest_history_metadata(self, world_id: str) -> Optional[Dict[str, Any]]:
        bucket = self._history_metadata.get(world_id)
        if not bucket:
            return None
        best_entry: Dict[str, Any] | None = None
        best_rank: Tuple[datetime, datetime] | None = None
        for value in bucket.values():
            rank = _metadata_rank(value)
            if best_rank is None or rank > best_rank:
                best_rank = rank
                best_entry = value
        return dict(best_entry) if best_entry else None

    async def record_rebalance_plan(self, payload: Dict[str, Any]) -> None:
        """Record a rebalancing plan into audit logs per world.

        Expected payload shape:
        {
            "per_world": { world_id: { ... plan ... } },
            "global_deltas": [ {symbol, delta_qty, venue?}, ... ],
        }
        """
        per_world = dict(payload.get("per_world", {}))
        for wid, plan in per_world.items():
            self._audit.append(
                wid,
                {
                    "event": "rebalancing_planned",
                    "world_id": wid,
                    "plan": plan,
                },
            )
        # Also append a summary entry under a virtual world id 'GLOBAL' for easy retrieval
        self._audit.append(
            "GLOBAL",
            {
                "event": "rebalancing_planned_global",
                "per_world_ids": sorted(per_world.keys()),
                "global_deltas": payload.get("global_deltas", []),
            },
        )

    async def get_allocation_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        record = self._allocation_runs.get(run_id)
        return None if record is None else record.to_dict()

    async def record_allocation_run(
        self,
        run_id: str,
        etag: str,
        payload: Dict[str, Any],
        *,
        executed: bool = False,
    ) -> None:
        record = AllocationRun(
            run_id=run_id,
            etag=etag,
            payload=payload,
            executed=executed,
            created_at=datetime_now(),
        )
        self._allocation_runs[run_id] = record

    async def record_evaluation_run(
        self,
        world_id: str,
        strategy_id: str,
        run_id: str,
        *,
        stage: str,
        risk_tier: str,
        model_card_version: str | None = None,
        metrics: Mapping[str, Any] | None = None,
        validation: Mapping[str, Any] | None = None,
        summary: Mapping[str, Any] | None = None,
        created_at: str | None = None,
        updated_at: str | None = None,
    ) -> Dict[str, Any]:
        now = updated_at or datetime_now()
        created = created_at or now
        record = EvaluationRunRecord(
            run_id=run_id,
            world_id=world_id,
            strategy_id=strategy_id,
            stage=stage,
            risk_tier=risk_tier,
            model_card_version=model_card_version,
            metrics=deepcopy(metrics) if metrics else {},
            validation=deepcopy(validation) if validation else {},
            summary=deepcopy(summary) if summary else {},
            created_at=created,
            updated_at=now,
        )
        self._evaluation_runs[(world_id, strategy_id, run_id)] = record
        history_key = (world_id, strategy_id, run_id)
        history = self._evaluation_run_history.setdefault(history_key, [])
        revision = len(history) + 1
        history.append(
            {
                "revision": revision,
                "recorded_at": now,
                "payload": record.to_dict(),
            }
        )
        self._audit.append(
            world_id,
            {
                "event": "evaluation_run_recorded",
                "strategy_id": strategy_id,
                "run_id": run_id,
                "stage": stage,
                "risk_tier": risk_tier,
            },
        )
        return record.to_dict()

    async def get_evaluation_run(
        self, world_id: str, strategy_id: str, run_id: str
    ) -> Optional[Dict[str, Any]]:
        record = self._evaluation_runs.get((world_id, strategy_id, run_id))
        return None if record is None else record.to_dict()

    async def record_evaluation_override(
        self,
        world_id: str,
        strategy_id: str,
        run_id: str,
        override: Mapping[str, Any],
    ) -> Dict[str, Any]:
        record = self._evaluation_runs.get((world_id, strategy_id, run_id))
        if record is None:
            raise KeyError("evaluation run not found")

        override_timestamp = str(override.get("timestamp") or datetime_now())
        summary = dict(record.summary or {})
        summary.update(
            {
                "override_status": override.get("status"),
                "override_reason": override.get("reason"),
                "override_actor": override.get("actor"),
                "override_timestamp": override_timestamp,
            }
        )
        updated = EvaluationRunRecord(
            run_id=record.run_id,
            world_id=record.world_id,
            strategy_id=record.strategy_id,
            stage=record.stage,
            risk_tier=record.risk_tier,
            model_card_version=record.model_card_version,
            metrics=deepcopy(record.metrics),
            validation=deepcopy(record.validation),
            summary=summary,
            created_at=record.created_at,
            updated_at=override_timestamp,
        )
        self._evaluation_runs[(world_id, strategy_id, run_id)] = updated
        history_key = (world_id, strategy_id, run_id)
        history = self._evaluation_run_history.setdefault(history_key, [])
        revision = len(history) + 1
        history.append(
            {
                "revision": revision,
                "recorded_at": override_timestamp,
                "payload": updated.to_dict(),
            }
        )
        self._audit.append(
            world_id,
            {
                "event": "evaluation_run_override_recorded",
                "strategy_id": strategy_id,
                "run_id": run_id,
                "status": override.get("status"),
                "actor": override.get("actor"),
                "timestamp": override_timestamp,
            },
        )
        payload = updated.to_dict()
        payload["revision"] = revision
        return payload

    async def list_evaluation_runs(
        self, *, world_id: str | None = None, strategy_id: str | None = None
    ) -> List[Dict[str, Any]]:
        runs: List[Dict[str, Any]] = []
        for (wid, sid, _), record in self._evaluation_runs.items():
            if world_id and wid != world_id:
                continue
            if strategy_id and sid != strategy_id:
                continue
            runs.append(record.to_dict())
        runs.sort(key=lambda entry: entry.get("created_at") or "")
        return runs

    async def list_evaluation_run_history(
        self, world_id: str, strategy_id: str, run_id: str
    ) -> List[Dict[str, Any]]:
        history = self._evaluation_run_history.get((world_id, strategy_id, run_id), [])
        return deepcopy(history)

    async def purge_evaluation_run_history(
        self,
        *,
        older_than: str,
        world_id: str | None = None,
        dry_run: bool = True,
    ) -> Dict[str, Any]:
        candidates = 0
        deleted = 0
        for (wid, sid, rid), history in list(self._evaluation_run_history.items()):
            if world_id and wid != world_id:
                continue
            kept: list[dict[str, Any]] = []
            for item in history:
                recorded_at = item.get("recorded_at")
                if isinstance(recorded_at, str) and recorded_at < older_than:
                    candidates += 1
                    if not dry_run:
                        deleted += 1
                        continue
                kept.append(item)
            if not dry_run:
                self._evaluation_run_history[(wid, sid, rid)] = kept
        return {
            "older_than": older_than,
            "world_id": world_id,
            "dry_run": dry_run,
            "candidates": candidates,
            "deleted": 0 if dry_run else deleted,
        }

    async def mark_allocation_run_executed(self, run_id: str) -> None:
        record = self._allocation_runs.get(run_id)
        if record is not None:
            self._allocation_runs[run_id] = AllocationRun(
                run_id=record.run_id,
                etag=record.etag,
                payload=deepcopy(record.payload),
                executed=True,
                created_at=record.created_at,
            )

    async def get_world_allocation_state(self, world_id: str) -> Optional[AllocationState]:
        state = self._world_allocations.get(world_id)
        return None if state is None else AllocationState(**state.to_dict())

    async def get_world_allocation_states(
        self, world_ids: Iterable[str] | None = None
    ) -> Dict[str, AllocationState]:
        targets = self._world_allocations if world_ids is None else {
            wid: self._world_allocations[wid]
            for wid in world_ids
            if wid in self._world_allocations
        }
        return {wid: AllocationState(**state.to_dict()) for wid, state in targets.items()}

    async def set_world_allocations(
        self,
        allocations: Mapping[str, float],
        *,
        run_id: str,
        etag: str,
        strategy_allocations: Mapping[str, Mapping[str, float]] | None = None,
        updated_at: str | None = None,
    ) -> None:
        ts = updated_at or datetime_now()
        for wid, ratio in allocations.items():
            strat_total = None
            if strategy_allocations and wid in strategy_allocations:
                strat_total = dict(strategy_allocations[wid])
            state = AllocationState(
                world_id=wid,
                allocation=float(ratio),
                run_id=run_id,
                etag=etag,
                strategy_alloc_total=strat_total,
                updated_at=ts,
            )
            self._world_allocations[wid] = state
            self._audit.append(
                wid,
                {
                    "event": "world_allocation_upserted",
                    "allocation": float(ratio),
                    "run_id": run_id,
                    "etag": etag,
                    "updated_at": ts,
                    "strategy_alloc_total": strat_total,
                },
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


def datetime_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _metadata_rank(payload: Dict[str, Any]) -> Tuple[datetime, datetime]:
    as_of = _parse_iso(payload.get("as_of")) or datetime.min.replace(tzinfo=timezone.utc)
    updated = _parse_iso(payload.get("updated_at")) or datetime.min.replace(tzinfo=timezone.utc)
    return as_of, updated


def _parse_iso(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        text = str(value)
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


__all__ = ["Storage"]
