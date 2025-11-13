"""Public service façade orchestrating world operations."""

from __future__ import annotations

from dataclasses import dataclass
import asyncio
import json
import logging
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Any, Dict, Iterable, Mapping

from fastapi import HTTPException

from qmtl.foundation.common.hashutils import hash_bytes

from .activation import ActivationEventPublisher
from .apply_flow import ApplyCoordinator
from .controlbus_producer import ControlBusProducer
from .decision import DecisionEvaluator, augment_metrics_with_linearity
from .policy import GatingPolicy
from .rebalancing import MultiWorldProportionalRebalancer, MultiWorldRebalanceContext, PositionSlice
from .run_state import ApplyRunRegistry, ApplyRunState, ApplyStage
from .schemas import (
    ActivationEnvelope,
    ActivationRequest,
    AllocationUpsertRequest,
    AllocationUpsertResponse,
    ApplyAck,
    ApplyRequest,
    ApplyResponse,
    EvaluateRequest,
    MultiWorldRebalanceRequest,
    PositionSliceModel,
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

    def _ensure_scaling_mode(self, payload: AllocationUpsertRequest) -> None:
        requested_mode = (payload.mode or "scaling").lower()
        if requested_mode in {"overlay", "hybrid"}:
            raise HTTPException(status_code=501, detail="Overlay mode is not implemented yet")

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
        context = MultiWorldRebalanceContext(
            total_equity=payload.total_equity,
            world_alloc_before=world_alloc_before,
            world_alloc_after=dict(payload.world_allocations),
            strategy_alloc_before_total=strategy_before or None,
            strategy_alloc_after_total=payload.strategy_alloc_after_total,
            positions=self._convert_positions(payload.positions),
            min_trade_notional=payload.min_trade_notional or 0.0,
            lot_size_by_symbol=payload.lot_size_by_symbol,
        )
        plan_result = self._multi_rebalancer.plan(context)
        plan_payload = self._serialize_plan(
            plan_result, schema_version=DEFAULT_REBALANCE_SCHEMA_VERSION
        )
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
        active = await self._evaluator.determine_active(world_id, payload)
        return ApplyResponse(active=active)

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
        self._ensure_scaling_mode(payload)

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
