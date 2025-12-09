"""Public service façade orchestrating world operations."""

from __future__ import annotations

from dataclasses import dataclass
import asyncio
import json
import logging
from contextlib import AsyncExitStack, asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Mapping, Optional

from fastapi import HTTPException

from qmtl.foundation.common.hashutils import hash_bytes
from qmtl.foundation.common.compute_context import canonicalize_world_mode

from .activation import ActivationEventPublisher
from .apply_flow import ApplyCoordinator
from .controlbus_producer import ControlBusProducer
from .decision import DecisionEvaluator, augment_metrics_with_linearity
from .policy import GatingPolicy
from .policy_engine import PolicyEvaluationResult
from .rebalancing import MultiWorldProportionalRebalancer, MultiWorldRebalanceContext, PositionSlice, SymbolDelta
from .rebalancing.overlay import OverlayConfigError, OverlayPlanner
from .run_state import ApplyRunRegistry, ApplyRunState, ApplyStage
from .schemas import (
    ActivationEnvelope,
    ActivationRequest,
    AllocationUpsertRequest,
    AllocationUpsertResponse,
    ApplyAck,
    ApplyRequest,
    ApplyResponse,
    DecisionEnvelope,
    EvaluateRequest,
    MultiWorldRebalanceRequest,
    PositionSliceModel,
    SeamlessArtifactPayload,
    StrategySeries,
)
from .storage import Storage


logger = logging.getLogger(__name__)

DEFAULT_REBALANCE_SCHEMA_VERSION = 1


@dataclass
class AllocationExecutionPlan:
    payload: AllocationUpsertRequest
    etag: str
    schema_version: int
    world_ids: tuple[str, ...]
    world_alloc_before: Dict[str, float]
    strategy_alloc_before: Dict[str, Dict[str, float]]
    plan_payload: Dict[str, Any]
    request_snapshot: Dict[str, Any]
    executed: bool = False
    execution_response: Any | None = None


@dataclass
class _DecisionState:
    """Cached decision inputs to support simple hysteresis."""

    effective_mode: str
    dataset_fingerprint: str | None = None


class WorldService:
    """Business logic helpers for the world service FastAPI application."""

    def __init__(
        self,
        store: Storage,
        bus: ControlBusProducer | None = None,
        rebalance_executor: Any | None = None,
    ) -> None:
        self.bus = bus
        self.rebalance_executor = rebalance_executor
        self._runs = ApplyRunRegistry()
        self.apply_runs = self._runs.runs
        self.apply_locks = self._runs.locks
        self._activation = ActivationEventPublisher(store, bus)
        self._evaluator = DecisionEvaluator(store)
        self._coordinator = ApplyCoordinator(
            store=store,
            bus=bus,
            evaluator=self._evaluator,
            activation=self._activation,
            runs=self._runs,
        )
        self.store = store
        self._allocation_locks: Dict[str, asyncio.Lock] = {}
        self._multi_rebalancer = MultiWorldProportionalRebalancer()
        self._decisions: Dict[str, _DecisionState] = {}

    @property
    def store(self) -> Storage:
        return self._store

    @store.setter
    def store(self, value: Storage) -> None:
        self._store = value
        self._activation.store = value
        self._evaluator.store = value
        self._coordinator.store = value

    def _allocation_lock_for(self, world_id: str) -> asyncio.Lock:
        lock = self._allocation_locks.get(world_id)
        if lock is None:
            lock = asyncio.Lock()
            self._allocation_locks[world_id] = lock
        return lock

    def _validate_allocation_payload(self, payload: AllocationUpsertRequest) -> None:
        if not payload.world_allocations:
            raise HTTPException(status_code=422, detail="world_allocations cannot be empty")
        invalid = [wid for wid, val in payload.world_allocations.items() if val < 0 or val > 1]
        if invalid:
            raise HTTPException(
                status_code=422,
                detail=f"Allocation ratios must be between 0 and 1: {', '.join(sorted(invalid))}",
            )

    def _ensure_supported_mode(self, payload: AllocationUpsertRequest) -> None:
        requested_mode = (payload.mode or "scaling").lower()
        if requested_mode == "hybrid":
            raise HTTPException(
                status_code=501, detail="Hybrid mode is not implemented yet. Use mode='scaling' or 'overlay'."
            )
        if requested_mode == "overlay" and payload.overlay is None:
            raise HTTPException(
                status_code=422, detail="overlay config is required when mode='overlay'"
            )

    async def _build_allocation_context(
        self, payload: AllocationUpsertRequest, world_ids: list[str]
    ) -> tuple[Dict[str, float], Dict[str, Dict[str, float]]]:
        states = await self.store.get_world_allocation_states(world_ids)
        world_alloc_before: Dict[str, float] = {
            wid: states[wid].allocation if wid in states else 0.0 for wid in world_ids
        }
        strategy_before: Dict[str, Dict[str, float]] = {}
        for wid, state in states.items():
            if state.strategy_alloc_total:
                strategy_before[wid] = dict(state.strategy_alloc_total)
        if payload.strategy_alloc_before_total:
            for wid, mapping in payload.strategy_alloc_before_total.items():
                strategy_before[wid] = dict(mapping)
        return world_alloc_before, strategy_before

    def _build_allocation_execution_plan(
        self,
        payload: AllocationUpsertRequest,
        etag: str,
        world_ids: list[str],
        world_alloc_before: Dict[str, float],
        strategy_before: Dict[str, Dict[str, float]],
    ) -> AllocationExecutionPlan:
        positions = self._convert_positions(payload.positions)
        context = MultiWorldRebalanceContext(
            total_equity=payload.total_equity,
            world_alloc_before=world_alloc_before,
            world_alloc_after=dict(payload.world_allocations),
            strategy_alloc_before_total=strategy_before or None,
            strategy_alloc_after_total=payload.strategy_alloc_after_total,
            positions=positions,
            min_trade_notional=payload.min_trade_notional or 0.0,
            lot_size_by_symbol=payload.lot_size_by_symbol,
        )
        plan_result = self._multi_rebalancer.plan(context)
        overlay_deltas = self._plan_overlay(
            payload=payload, context=context, plan_result=plan_result
        )
        plan_payload = self._serialize_plan(
            plan_result, schema_version=DEFAULT_REBALANCE_SCHEMA_VERSION
        )
        if overlay_deltas is not None:
            plan_payload["overlay_deltas"] = [
                {
                    "symbol": d.symbol,
                    "delta_qty": d.delta_qty,
                    "venue": d.venue,
                }
                for d in overlay_deltas
            ]
        request_snapshot = MultiWorldRebalanceRequest(
            total_equity=payload.total_equity,
            world_alloc_before=world_alloc_before,
            world_alloc_after=dict(payload.world_allocations),
            positions=payload.positions,
            strategy_alloc_before_total=strategy_before or None,
            strategy_alloc_after_total=payload.strategy_alloc_after_total,
            min_trade_notional=payload.min_trade_notional,
            lot_size_by_symbol=payload.lot_size_by_symbol,
            mode=payload.mode,
            overlay=payload.overlay,
            schema_version=DEFAULT_REBALANCE_SCHEMA_VERSION,
        ).model_dump(exclude_none=True)
        return AllocationExecutionPlan(
            payload=payload,
            etag=etag,
            schema_version=DEFAULT_REBALANCE_SCHEMA_VERSION,
            world_ids=tuple(world_ids),
            world_alloc_before=world_alloc_before,
            strategy_alloc_before=strategy_before,
            plan_payload=plan_payload,
            request_snapshot=request_snapshot,
        )

    async def _persist_allocation_plan(self, plan: AllocationExecutionPlan) -> None:
        await self.store.record_allocation_run(
            plan.payload.run_id,
            plan.etag,
            {
                "plan": plan.plan_payload,
                "request": plan.request_snapshot,
            },
            executed=False,
        )
        await self.store.set_world_allocations(
            plan.payload.world_allocations,
            run_id=plan.payload.run_id,
            etag=plan.etag,
            strategy_allocations=plan.payload.strategy_alloc_after_total,
        )
        await self.store.record_rebalance_plan(plan.plan_payload)
        if self.bus is not None:
            alpha_metrics = plan.plan_payload.get("alpha_metrics")
            intent = plan.plan_payload.get("rebalance_intent")
            for wid, per_plan in plan.plan_payload["per_world"].items():
                try:
                    await self.bus.publish_rebalancing_plan(
                        wid,
                        per_plan,
                        version=plan.schema_version,
                        schema_version=plan.schema_version,
                        alpha_metrics=alpha_metrics,
                        rebalance_intent=intent,
                    )
                except Exception:  # pragma: no cover - best effort
                    logger.exception("Failed to publish rebalancing plan for %s", wid)

    async def _maybe_execute_allocation_plan(
        self, plan: AllocationExecutionPlan
    ) -> AllocationExecutionPlan:
        if not plan.payload.execute:
            return plan
        response = await self._execute_rebalance(plan.request_snapshot)
        plan.execution_response = response
        plan.executed = True
        await self.store.mark_allocation_run_executed(plan.payload.run_id)
        return plan

    @asynccontextmanager
    async def _lock_worlds(self, world_ids: list[str]):
        async with AsyncExitStack() as stack:
            for wid in world_ids:
                await stack.enter_async_context(self._allocation_lock_for(wid))
            yield

    async def _plan_and_persist_allocation(
        self,
        payload: AllocationUpsertRequest,
        etag: str,
        world_ids: list[str],
        world_alloc_before: Dict[str, float],
        strategy_before: Dict[str, Dict[str, float]],
    ) -> AllocationExecutionPlan:
        plan = self._build_allocation_execution_plan(
            payload, etag, world_ids, world_alloc_before, strategy_before
        )
        await self._persist_allocation_plan(plan)
        return plan

    async def _handle_existing_allocation_run(
        self,
        payload: AllocationUpsertRequest,
        etag: str,
        existing_run: Mapping[str, Any],
    ) -> AllocationUpsertResponse:
        stored_etag = existing_run.get("etag")
        if stored_etag and stored_etag != etag:
            raise HTTPException(status_code=409, detail="run_id already used with a different payload")

        record_payload = existing_run.get("payload", {})
        plan_payload = record_payload.get("plan", record_payload)
        request_snapshot = record_payload.get("request")
        executed = bool(existing_run.get("executed", False))
        execution_response: Any | None = None

        if payload.execute and not executed:
            if request_snapshot is None:
                request_snapshot = payload.model_dump(
                    exclude={"run_id", "etag"},
                    exclude_none=True,
                )
            execution_response = await self._execute_rebalance(request_snapshot)
            await self.store.mark_allocation_run_executed(payload.run_id)
            executed = True

        return AllocationUpsertResponse(
            run_id=payload.run_id,
            etag=stored_etag or etag,
            executed=executed,
            execution_response=execution_response,
            **plan_payload,
        )

    async def evaluate(self, world_id: str, payload: EvaluateRequest) -> ApplyResponse:
        evaluation = await self._evaluator.determine_active(world_id, payload)
        active = list(evaluation)
        run_id, strategy_id = await self._maybe_record_evaluation_run(world_id, payload, evaluation)
        eval_url = (
            self._build_evaluation_run_url(world_id, strategy_id, run_id)
            if run_id and strategy_id
            else None
        )
        return ApplyResponse(
            active=active,
            evaluation_run_id=run_id,
            evaluation_run_url=eval_url,
        )

    async def _maybe_record_evaluation_run(
        self,
        world_id: str,
        payload: EvaluateRequest,
        evaluation: PolicyEvaluationResult | None,
    ) -> tuple[str | None, str | None]:
        strategy_id = self._resolve_strategy_id(payload)
        if strategy_id is None:
            return None, None

        run_id = payload.run_id or self._default_evaluation_run_id(strategy_id)
        stage = (payload.stage or "backtest").lower()
        risk_tier = (payload.risk_tier or "unknown").lower()
        metrics = self._extract_metrics(payload, strategy_id)
        validation_payload = self._extract_validation_payload(payload)
        rule_results = evaluation.for_strategy(strategy_id) if evaluation else {}
        if rule_results:
            validation_payload = validation_payload or {}
            validation_payload["results"] = {
                name: result.model_dump() for name, result in rule_results.items()
            }
        if evaluation and evaluation.profile:
            validation_payload = validation_payload or {}
            validation_payload.setdefault("profile", evaluation.profile)
        active_flag = strategy_id in (evaluation.selected if evaluation else [])
        summary = {
            "status": "pass" if active_flag else "fail",
            "active": active_flag,
            "active_set": list(evaluation.selected if evaluation else []),
        }

        try:
            await self.store.record_evaluation_run(
                world_id,
                strategy_id,
                run_id,
                stage=stage,
                risk_tier=risk_tier,
                metrics=metrics,
                validation=validation_payload,
                summary=summary,
            )
        except Exception:  # pragma: no cover - defensive best-effort
            logger.exception("Failed to record evaluation run for %s/%s", world_id, strategy_id)

        return run_id, strategy_id

    @staticmethod
    def _resolve_strategy_id(payload: EvaluateRequest) -> str | None:
        if payload.strategy_id:
            return payload.strategy_id
        if payload.metrics:
            try:
                return next(iter(payload.metrics.keys()))
            except StopIteration:
                return None
        return None

    @staticmethod
    def _extract_metrics(payload: EvaluateRequest, strategy_id: str) -> dict[str, float]:
        metrics = payload.metrics or {}
        strategy_metrics = metrics.get(strategy_id)
        if not isinstance(strategy_metrics, dict):
            return {}
        # Normalize to EvaluationMetrics shape; if already structured, pass through.
        structured_keys = {"returns", "sample", "risk", "robustness", "diagnostics"}
        if structured_keys & set(strategy_metrics.keys()):
            return dict(strategy_metrics)
        return {"returns": dict(strategy_metrics)}

    @staticmethod
    def _extract_validation_payload(payload: EvaluateRequest) -> dict | None:
        if payload.policy is None:
            return None
        try:
            return payload.policy.model_dump()  # type: ignore[union-attr]
        except Exception:
            return payload.policy if isinstance(payload.policy, dict) else None

    @staticmethod
    def _default_evaluation_run_id(strategy_id: str) -> str:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        return f"eval-{strategy_id}-{ts}"

    @staticmethod
    def _build_evaluation_run_url(world_id: str, strategy_id: str | None, run_id: str | None) -> str | None:
        if strategy_id is None or run_id is None:
            return None
        return f"/worlds/{world_id}/strategies/{strategy_id}/runs/{run_id}"

    async def decide(self, world_id: str) -> DecisionEnvelope:
        now = datetime.now(timezone.utc)
        world = await self.store.get_world(world_id)
        if world is None:
            raise HTTPException(status_code=404, detail="world not found")

        version = await self.store.default_policy_version(world_id)
        bindings = await self.store.list_bindings(world_id)
        decisions = await self.store.get_decisions(world_id)
        metadata = await self.store.latest_history_metadata(world_id)

        normalized_metadata = self._normalize_metadata(metadata)
        allow_live = bool(world.get("allow_live", False))

        evaluation = self._evaluate_policy(
            allow_live=allow_live,
            has_bindings=bool(bindings),
            has_decisions=bool(decisions),
            metadata=normalized_metadata,
            world_id=world_id,
        )

        etag = self._build_decision_etag(
            world_id,
            version,
            normalized_metadata.get("dataset_fingerprint"),
            normalized_metadata.get("as_of"),
            normalized_metadata.get("history_updated_at"),
            now,
        )

        return DecisionEnvelope(
            world_id=world_id,
            policy_version=version,
            effective_mode=evaluation["effective_mode"],
            reason=evaluation["reason"],
            as_of=normalized_metadata.get("as_of", evaluation["as_of_fallback"]),
            ttl=evaluation["ttl"],
            etag=etag,
            dataset_fingerprint=normalized_metadata.get("dataset_fingerprint"),
            coverage_bounds=normalized_metadata.get("coverage_bounds"),
            conformance_flags=normalized_metadata.get("conformance_flags"),
            conformance_warnings=normalized_metadata.get("conformance_warnings"),
            history_updated_at=normalized_metadata.get("history_updated_at"),
            rows=normalized_metadata.get("rows"),
            artifact=normalized_metadata.get("artifact"),
        )

    async def apply(
        self,
        world_id: str,
        payload: ApplyRequest,
        gating: GatingPolicy | None,
    ) -> ApplyAck:
        lock = self._runs.lock_for(world_id)
        async with lock:
            return await self._coordinator.apply(world_id, payload, gating)

    async def upsert_activation(self, world_id: str, payload: ActivationRequest) -> ActivationEnvelope:
        data = await self._activation.upsert_activation(
            world_id, payload.model_dump(exclude_unset=True)
        )
        return ActivationEnvelope(
            world_id=world_id,
            strategy_id=payload.strategy_id,
            side=payload.side,
            **data,
        )

    @staticmethod
    def augment_metrics_with_linearity(
        metrics: Dict[str, Dict[str, float]],
        series: Dict[str, StrategySeries] | None,
    ) -> Dict[str, Dict[str, float]]:
        return augment_metrics_with_linearity(metrics, series)

    def _normalize_metadata(
        self, metadata: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        if not metadata:
            return {}

        normalized: Dict[str, Any] = {}
        dataset_fp = metadata.get("dataset_fingerprint")
        if dataset_fp:
            normalized["dataset_fingerprint"] = str(dataset_fp)

        as_of_value = metadata.get("as_of")
        if as_of_value:
            normalized["as_of"] = str(as_of_value)

        updated_at = metadata.get("updated_at")
        if updated_at:
            normalized["history_updated_at"] = updated_at

        rows = metadata.get("rows")
        if rows is not None:
            try:
                normalized["rows"] = int(rows)
            except Exception:
                normalized["rows"] = rows

        raw_cov = metadata.get("coverage_bounds")
        if isinstance(raw_cov, (list, tuple)):
            normalized["coverage_bounds"] = [int(v) for v in raw_cov]

        raw_flags = metadata.get("conformance_flags")
        if isinstance(raw_flags, dict):
            normalized["conformance_flags"] = dict(raw_flags)

        raw_warnings = metadata.get("conformance_warnings")
        if raw_warnings is not None:
            normalized["conformance_warnings"] = [str(v) for v in raw_warnings]

        artifact_payload = metadata.get("artifact")
        if isinstance(artifact_payload, dict):
            normalized["artifact"] = SeamlessArtifactPayload.model_validate(
                artifact_payload
            )
            if normalized["artifact"].as_of and not normalized.get("as_of"):
                normalized["as_of"] = str(normalized["artifact"].as_of)
            if normalized.get("rows") is None and normalized["artifact"].rows is not None:
                normalized["rows"] = int(normalized["artifact"].rows)  # type: ignore[arg-type]

        return normalized

    def _evaluate_policy(
        self,
        *,
        allow_live: bool,
        has_bindings: bool,
        has_decisions: bool,
        metadata: Dict[str, Any],
        world_id: str,
    ) -> Dict[str, Any]:
        reasons: list[str] = []
        ttl = "60s"
        as_of_fallback = (
            datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        )
        dataset_fp = metadata.get("dataset_fingerprint")
        metrics_ok = bool(
            metadata.get("coverage_bounds")
            or metadata.get("conformance_flags")
            or metadata.get("rows")
        )

        if not has_bindings:
            reasons.append("no_bindings")
            effective_mode = "validate"
        elif not has_decisions:
            reasons.append("no_active_strategies")
            effective_mode = "validate"
        else:
            reasons.append("bindings_present")
            reasons.append("decisions_present")
            hysteresis = False
            previous = self._decisions.get(world_id)
            if previous and previous.effective_mode == "live":
                hysteresis = previous.dataset_fingerprint == dataset_fp

            if allow_live and dataset_fp and metrics_ok:
                reasons.extend(["allow_live", "dataset_fingerprint_ok", "metrics_ok"])
                effective_mode = "live"
                ttl = "300s"
            elif allow_live and hysteresis:
                reasons.extend(["allow_live", "hysteresis_hold"])
                effective_mode = "live"
                ttl = "120s"
            else:
                if not allow_live:
                    reasons.append("allow_live_disabled")
                if not dataset_fp:
                    reasons.append("dataset_fingerprint_missing")
                if not metrics_ok:
                    reasons.append("required_metrics_missing")
                effective_mode = "compute-only"

        canonical_mode = canonicalize_world_mode(effective_mode)
        reason_str = " & ".join(reasons) if reasons else "unspecified"
        self._decisions[world_id] = _DecisionState(
            effective_mode=canonical_mode, dataset_fingerprint=dataset_fp
        )
        return {
            "effective_mode": canonical_mode,
            "reason": reason_str,
            "ttl": ttl,
            "as_of_fallback": as_of_fallback,
        }

    @staticmethod
    def _build_decision_etag(
        world_id: str,
        version: int,
        dataset_fp: str | None,
        as_of_value: str | None,
        updated_at: Any,
        now: datetime,
    ) -> str:
        etag_parts = [f"w:{world_id}", f"v{version}"]
        if dataset_fp:
            etag_parts.append(str(dataset_fp))
        if as_of_value:
            etag_parts.append(str(as_of_value))
        if updated_at:
            etag_parts.append(str(updated_at))
        etag_parts.append(str(int(now.timestamp())))
        return ":".join(etag_parts)

    @staticmethod
    def _hash_allocation_payload(payload: AllocationUpsertRequest) -> str:
        basis = payload.model_dump(
            exclude={"run_id", "execute", "etag"},
            exclude_none=True,
        )
        serialized = json.dumps(basis, sort_keys=True, separators=(",", ":"))
        return hash_bytes(serialized.encode("utf-8"))

    @staticmethod
    def _convert_positions(models: Iterable[PositionSliceModel]) -> list[PositionSlice]:
        return [
            PositionSlice(
                world_id=m.world_id,
                strategy_id=m.strategy_id,
                symbol=m.symbol,
                qty=m.qty,
                mark=m.mark,
                venue=m.venue,
            )
            for m in models
        ]

    @staticmethod
    def _serialize_plan(
        result,
        *,
        schema_version: int = 1,
        alpha_metrics: Dict[str, Any] | None = None,
        rebalance_intent: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        per_world: Dict[str, Any] = {}
        for wid, plan in result.per_world.items():
            per_world[wid] = {
                "world_id": wid,
                "scale_world": plan.scale_world,
                "scale_by_strategy": dict(plan.scale_by_strategy),
                "deltas": [
                    {
                        "symbol": d.symbol,
                        "delta_qty": d.delta_qty,
                        "venue": d.venue,
                    }
                    for d in plan.deltas
                ],
            }
        global_deltas = [
            {"symbol": d.symbol, "delta_qty": d.delta_qty, "venue": d.venue}
            for d in result.global_deltas
        ]
        payload: Dict[str, Any] = {
            "schema_version": schema_version,
            "per_world": per_world,
            "global_deltas": global_deltas,
        }
        if alpha_metrics is not None:
            payload["alpha_metrics"] = alpha_metrics
        if rebalance_intent is not None:
            payload["rebalance_intent"] = rebalance_intent
        return payload

    def _plan_overlay(
        self,
        *,
        payload: AllocationUpsertRequest,
        context: MultiWorldRebalanceContext,
        plan_result,
    ) -> list[SymbolDelta] | None:
        mode = (payload.mode or "scaling").lower()
        if mode != "overlay":
            return None
        if payload.overlay is None:
            raise HTTPException(
                status_code=422, detail="overlay config is required when mode='overlay'"
            )
        try:
            return OverlayPlanner().plan(
                positions=context.positions,
                world_alloc_before=context.world_alloc_before,
                world_alloc_after=context.world_alloc_after,
                overlay=payload.overlay,
                scale_by_world={wid: plan.scale_world for wid, plan in plan_result.per_world.items()},
            )
        except OverlayConfigError as exc:
            raise HTTPException(status_code=422, detail=str(exc))

    async def _execute_rebalance(
        self,
        request_payload: Mapping[str, Any],
    ) -> Any:
        if self.rebalance_executor is None:
            raise HTTPException(status_code=503, detail="Rebalance executor not configured")
        try:
            return await self.rebalance_executor.execute(dict(request_payload))
        except HTTPException:
            raise
        except Exception as exc:  # pragma: no cover - defensive propagation
            raise HTTPException(status_code=502, detail="Rebalance execution failed") from exc

    async def upsert_allocations(self, payload: AllocationUpsertRequest) -> AllocationUpsertResponse:
        self._validate_allocation_payload(payload)
        self._ensure_supported_mode(payload)

        etag = self._hash_allocation_payload(payload)
        existing_run = await self.store.get_allocation_run(payload.run_id)
        if existing_run is not None:
            return await self._handle_existing_allocation_run(payload, etag, existing_run)

        world_ids = sorted(payload.world_allocations.keys())

        async with self._lock_worlds(world_ids):
            world_alloc_before, strategy_before = await self._build_allocation_context(
                payload, world_ids
            )
            plan = await self._plan_and_persist_allocation(
                payload, etag, world_ids, world_alloc_before, strategy_before
            )
            plan = await self._maybe_execute_allocation_plan(plan)

        return AllocationUpsertResponse(
            run_id=payload.run_id,
            etag=plan.etag,
            executed=plan.executed,
            execution_response=plan.execution_response,
            **plan.plan_payload,
        )


__all__ = [
    "ApplyRunRegistry",
    "ApplyRunState",
    "ApplyStage",
    "WorldService",
]
