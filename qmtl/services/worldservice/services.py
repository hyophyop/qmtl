"""Public service façade orchestrating world operations."""

from __future__ import annotations

from typing import Dict

from .activation import ActivationEventPublisher
from .apply_flow import ApplyCoordinator
from .controlbus_producer import ControlBusProducer
from .decision import DecisionEvaluator, augment_metrics_with_linearity
from .policy import GatingPolicy
from .run_state import ApplyRunRegistry, ApplyRunState, ApplyStage
from .schemas import (
    ActivationEnvelope,
    ActivationRequest,
    ApplyAck,
    ApplyRequest,
    ApplyResponse,
    EvaluateRequest,
    StrategySeries,
)
from .storage import Storage


class WorldService:
    """Business logic helpers for the world service FastAPI application."""

    def __init__(self, store: Storage, bus: ControlBusProducer | None = None) -> None:
        self.bus = bus
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

    @property
    def store(self) -> Storage:
        return self._store

    @store.setter
    def store(self, value: Storage) -> None:
        self._store = value
        self._activation.store = value
        self._evaluator.store = value
        self._coordinator.store = value

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


__all__ = [
    "ApplyRunRegistry",
    "ApplyRunState",
    "ApplyStage",
    "WorldService",
]
