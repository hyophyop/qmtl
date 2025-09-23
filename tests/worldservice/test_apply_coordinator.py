from __future__ import annotations

import copy
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from qmtl.services.worldservice.apply_flow import ApplyCoordinator
from qmtl.services.worldservice.decision import DecisionEvaluator
from qmtl.services.worldservice.policy import GatingPolicy
from qmtl.services.worldservice.run_state import ApplyRunRegistry, ApplyStage
from qmtl.services.worldservice.schemas import ApplyPlan, ApplyRequest


class _StubActivationPublisher:
    def __init__(self) -> None:
        self.freeze_calls: list[tuple[str, str]] = []
        self.unfreeze_calls: list[tuple[str, str, tuple[str, ...]]] = []

    async def freeze_world(self, world_id: str, run_id: str, snapshot, state) -> None:
        self.freeze_calls.append((world_id, run_id))

    async def unfreeze_world(
        self, world_id: str, run_id: str, snapshot, state, target_active
    ) -> None:
        self.unfreeze_calls.append((world_id, run_id, tuple(target_active)))


class _StubBus:
    def __init__(self) -> None:
        self.events: list[tuple[str, str, dict]] = []

    async def publish_policy_update(
        self,
        world_id: str,
        policy_version: int,
        checksum: str,
        status: str,
        ts: str,
        *,
        version: int,
    ) -> None:
        self.events.append(
            (
                world_id,
                status,
                {
                    "policy_version": policy_version,
                    "checksum": checksum,
                    "ts": ts,
                    "version": version,
                },
            )
        )


class _StubStore:
    def __init__(self) -> None:
        self.decisions = ["alpha"]
        self.snapshot_state = {
            "alpha": {"long": {"weight": 1.0, "effective_mode": "paper"}}
        }
        self.edge_overrides: dict[tuple[str, str, str], dict | None] = {}
        self.apply_stages: list[tuple[str, dict]] = []
        self.failures_remaining = 0

    async def get_decisions(self, world_id: str):
        return list(self.decisions)

    async def set_decisions(self, world_id: str, strategies: list[str]) -> None:
        if self.failures_remaining:
            self.failures_remaining -= 1
            raise RuntimeError("forced failure")
        self.decisions = list(strategies)

    async def snapshot_activation(self, world_id: str):
        return SimpleNamespace(state=copy.deepcopy(self.snapshot_state))

    async def restore_activation(self, world_id: str, snapshot) -> None:
        self.snapshot_state = copy.deepcopy(snapshot.state)

    async def record_apply_stage(self, world_id: str, run_id: str, stage: str, **details):
        self.apply_stages.append((stage, details))

    async def default_policy_version(self, world_id: str) -> int:
        return 1

    async def get_edge_override(self, world_id: str, src: str, dst: str):
        return self.edge_overrides.get((world_id, src, dst))

    async def upsert_edge_override(
        self,
        world_id: str,
        src: str,
        dst: str,
        *,
        active: bool,
        reason: str | None,
    ):
        entry = {"active": active, "reason": reason}
        self.edge_overrides[(world_id, src, dst)] = entry
        return entry

    async def delete_edge_override(self, world_id: str, src: str, dst: str) -> None:
        self.edge_overrides.pop((world_id, src, dst), None)


def _gating_policy() -> GatingPolicy:
    return GatingPolicy.model_validate(
        {
            "dataset_fingerprint": "ohlcv:demo",
            "share_policy": "feature-artifacts-only",
            "snapshot": {"strategy_plane": "cow", "feature_plane": "readonly"},
            "edges": {
                "pre_promotion": {"disable_edges_to": "live"},
                "post_promotion": {"enable_edges_to": ["live"]},
            },
            "observability": {"slo": {"cross_context_cache_hit": 0}},
        }
    )


def _make_request(run_id: str) -> ApplyRequest:
    return ApplyRequest(run_id=run_id, plan=ApplyPlan(activate=["beta"]))


@pytest.mark.asyncio
async def test_apply_coordinator_applies_gating_overrides() -> None:
    store = _StubStore()
    runs = ApplyRunRegistry()
    activation = _StubActivationPublisher()
    bus = _StubBus()
    coordinator = ApplyCoordinator(
        store=store,
        bus=bus,
        evaluator=DecisionEvaluator(store),
        activation=activation,
        runs=runs,
    )

    ack = await coordinator.apply("world", _make_request("run-1"), _gating_policy())

    assert ack.phase == "completed"
    assert runs.get("world").stage is ApplyStage.COMPLETED
    key = ("world", "domain:backtest", "domain:live")
    assert store.edge_overrides[key]["reason"] == "post_promotion_enable:run-1"
    assert activation.freeze_calls and activation.unfreeze_calls
    assert bus.events[0][0] == "world"


@pytest.mark.asyncio
async def test_apply_coordinator_rolls_back_and_clears_state() -> None:
    store = _StubStore()
    store.failures_remaining = 1
    runs = ApplyRunRegistry()
    coordinator = ApplyCoordinator(
        store=store,
        bus=None,
        evaluator=DecisionEvaluator(store),
        activation=_StubActivationPublisher(),
        runs=runs,
    )

    with pytest.raises(HTTPException) as exc:
        await coordinator.apply("world", _make_request("run-err"), None)
    assert exc.value.status_code == 500

    state = runs.get("world")
    assert state is not None
    assert state.stage is ApplyStage.ROLLED_BACK

    store.failures_remaining = 0
    ack = await coordinator.apply("world", _make_request("run-ok"), None)
    assert ack.phase == "completed"
    assert runs.get("world").stage is ApplyStage.COMPLETED
