"""Apply flow orchestration primitives."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, NoReturn

from fastapi import HTTPException

from qmtl.foundation.common.hashutils import hash_bytes

from .activation import ActivationEventPublisher
from .controlbus_producer import ControlBusProducer
from .decision import DecisionEvaluator
from .edge_overrides import EdgeOverrideManager, EdgeOverridePlan
from .policy import GatingPolicy
from .run_state import ApplyRunRegistry, ApplyRunState, ApplyStage
from .schemas import ApplyAck, ApplyRequest
from .storage import Storage, WorldActivation


@dataclass(slots=True)
class ApplyContext:
    world_id: str
    payload: ApplyRequest
    gating: GatingPolicy | None
    plan: EdgeOverridePlan
    target_active: List[str]
    snapshot_full: WorldActivation
    snapshot_view: Dict[str, Dict[str, Dict[str, Any]]]
    previous_decisions: List[str]


class ApplyCoordinator:
    """Coordinate the multi-stage apply lifecycle."""

    def __init__(
        self,
        *,
        store: Storage,
        bus: ControlBusProducer | None,
        evaluator: DecisionEvaluator,
        activation: ActivationEventPublisher,
        runs: ApplyRunRegistry,
    ) -> None:
        self.store = store
        self.bus = bus
        self._evaluator = evaluator
        self._activation = activation
        self._runs = runs

    async def apply(
        self,
        world_id: str,
        payload: ApplyRequest,
        gating: GatingPolicy | None,
    ) -> ApplyAck:
        existing = self._runs.get(world_id)
        if existing:
            ack = self._ack_for_existing(world_id, existing, payload.run_id)
            if ack:
                return ack

        plan = self._plan_for(gating)
        context = await self._build_context(world_id, payload, gating, plan)
        state = self._runs.start(world_id, payload.run_id, context.target_active)
        await self._record_requested(context, state)

        edge_manager = EdgeOverrideManager(self.store, world_id)
        try:
            if plan.pre_disable:
                await edge_manager.apply_pre_promotion(plan.pre_disable, payload.run_id)

            await self._enter_freeze(context, state)
            await self._switch_decisions(context, state)
            await self._notify_policy_update(context)
            await self._exit_freeze(context, state)

            if plan.post_enable:
                await edge_manager.apply_post_promotion(plan.post_enable, payload.run_id)

            state.mark(ApplyStage.COMPLETED, completed=True)
            await self.store.record_apply_stage(
                context.world_id,
                context.payload.run_id,
                ApplyStage.COMPLETED.value,
            )
            return ApplyAck(
                run_id=payload.run_id,
                active=list(context.target_active),
                phase=ApplyStage.COMPLETED.value,
            )
        except HTTPException:
            await edge_manager.restore()
            raise
        except Exception as exc:  # pragma: no cover - defensive fallback
            await edge_manager.restore()
            await self._handle_failure(context, state, exc)

    def _ack_for_existing(
        self, world_id: str, state: ApplyRunState, incoming_run_id: str
    ) -> ApplyAck | None:
        if not state.completed:
            if state.run_id == incoming_run_id:
                if state.stage is ApplyStage.ROLLED_BACK:
                    return ApplyAck(
                        ok=False,
                        run_id=state.run_id,
                        active=list(state.active),
                        phase=state.stage.value,
                    )
                return ApplyAck(
                    run_id=state.run_id,
                    active=list(state.active),
                    phase=state.stage.value,
                )
            if state.stage is ApplyStage.ROLLED_BACK:
                self._runs.remove(world_id)
            else:
                raise HTTPException(status_code=409, detail="apply in progress")
        elif state.run_id == incoming_run_id:
            return ApplyAck(
                run_id=state.run_id,
                active=list(state.active),
                phase=ApplyStage.COMPLETED.value,
            )
        return None

    def _plan_for(self, gating: GatingPolicy | None) -> EdgeOverridePlan:
        try:
            return EdgeOverrideManager.plan_for(gating)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    async def _build_context(
        self,
        world_id: str,
        payload: ApplyRequest,
        gating: GatingPolicy | None,
        plan: EdgeOverridePlan,
    ) -> ApplyContext:
        target_active = await self._evaluator.determine_active(world_id, payload)
        previous_decisions = list(await self.store.get_decisions(world_id))
        snapshot_full = await self.store.snapshot_activation(world_id)
        snapshot_view = {
            "state": {
                sid: {side: dict(entry) for side, entry in sides.items()}
                for sid, sides in snapshot_full.state.items()
            }
        }
        return ApplyContext(
            world_id=world_id,
            payload=payload,
            gating=gating,
            plan=plan,
            target_active=list(target_active),
            snapshot_full=snapshot_full,
            snapshot_view=snapshot_view,
            previous_decisions=previous_decisions,
        )

    async def _record_requested(
        self, context: ApplyContext, state: ApplyRunState
    ) -> None:
        state.mark(ApplyStage.REQUESTED, completed=False, active=context.target_active)
        await self.store.record_apply_stage(
            context.world_id,
            context.payload.run_id,
            ApplyStage.REQUESTED.value,
            plan=context.payload.plan.model_dump() if context.payload.plan else None,
            active=list(context.target_active),
            gating_policy=(
                context.gating.model_dump() if isinstance(context.gating, GatingPolicy) else None
            ),
        )

    async def _enter_freeze(self, context: ApplyContext, state: ApplyRunState) -> None:
        state.mark(ApplyStage.FREEZE)
        await self._activation.freeze_world(
            context.world_id,
            context.payload.run_id,
            context.snapshot_view,
            state,
        )
        await self.store.record_apply_stage(
            context.world_id,
            context.payload.run_id,
            ApplyStage.FREEZE.value,
        )

    async def _switch_decisions(self, context: ApplyContext, state: ApplyRunState) -> None:
        await self.store.set_decisions(context.world_id, list(context.target_active))
        state.mark(ApplyStage.SWITCH)
        await self.store.record_apply_stage(
            context.world_id,
            context.payload.run_id,
            ApplyStage.SWITCH.value,
            active=list(context.target_active),
        )

    async def _notify_policy_update(self, context: ApplyContext) -> None:
        if not self.bus:
            return
        version = await self.store.default_policy_version(context.world_id)
        sorted_active = sorted(context.target_active)
        digest_payload = json.dumps(sorted_active).encode()
        checksum = hash_bytes(digest_payload)
        ts = datetime.now(timezone.utc).isoformat()
        await self.bus.publish_policy_update(
            context.world_id,
            policy_version=version,
            checksum=checksum,
            status="ACTIVE",
            ts=ts,
            version=version,
        )

    async def _exit_freeze(self, context: ApplyContext, state: ApplyRunState) -> None:
        state.mark(ApplyStage.UNFREEZE)
        await self._activation.unfreeze_world(
            context.world_id,
            context.payload.run_id,
            context.snapshot_view,
            state,
            context.target_active,
        )
        await self.store.record_apply_stage(
            context.world_id,
            context.payload.run_id,
            ApplyStage.UNFREEZE.value,
        )

    async def _handle_failure(
        self, context: ApplyContext, state: ApplyRunState, exc: Exception
    ) -> NoReturn:
        await self.store.restore_activation(context.world_id, context.snapshot_full)
        await self.store.set_decisions(context.world_id, list(context.previous_decisions))
        await self.store.record_apply_stage(
            context.world_id,
            context.payload.run_id,
            ApplyStage.ROLLED_BACK.value,
            error=str(exc),
            active=list(context.previous_decisions),
        )
        restored = await self.store.snapshot_activation(context.world_id)
        restored_view = {
            "state": {
                sid: {side: dict(entry) for side, entry in sides.items()}
                for sid, sides in restored.state.items()
            }
        }
        await self._activation.freeze_world(
            context.world_id,
            context.payload.run_id,
            restored_view,
            state,
        )
        state.mark(
            ApplyStage.ROLLED_BACK,
            completed=False,
            active=context.previous_decisions,
        )
        raise HTTPException(status_code=500, detail="apply failed") from exc

__all__ = ["ApplyCoordinator", "ApplyContext"]
