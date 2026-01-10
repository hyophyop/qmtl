from __future__ import annotations

import pytest

from qmtl.runtime.sdk import Runner
from .stack import CoreLoopStackHandle, InProcessCoreLoopStack
from .worlds.core_loop_demo_strategy import CoreLoopDemoStrategy

pytestmark = pytest.mark.contract


def _world_id_candidates(world_id: str) -> set[str]:
    return {world_id, world_id.replace("_", "-"), world_id.replace("-", "_")}


def test_runner_submit_populates_ws_envelopes(
    core_loop_stack: CoreLoopStackHandle,
    core_loop_world_id: str,
):
    result = Runner.submit(
        CoreLoopDemoStrategy,
        world=core_loop_world_id,
        auto_validate=False,
    )

    assert result.decision is not None
    assert result.activation is not None
    assert result.decision.world_id in _world_id_candidates(core_loop_world_id)
    assert result.activation.world_id in _world_id_candidates(core_loop_world_id)
    assert result.strategy_id == result.activation.strategy_id

    if core_loop_stack.mode == "inproc":
        assert result.downgraded is False
        assert result.safe_mode is False


def test_runner_submit_downgrades_when_worldservice_unavailable(
    core_loop_worlds_dir,
    monkeypatch: pytest.MonkeyPatch,
):
    stack = InProcessCoreLoopStack(core_loop_worlds_dir)
    handle = stack.start()
    try:
        if not handle.world_ids:
            pytest.skip("no seeded world ids available for downgrade contract test")
        if handle.stop_worldservice is None:
            pytest.skip("worldservice stop hook not available")

        handle.stop_worldservice()
        monkeypatch.setenv("QMTL_GATEWAY_URL", handle.gateway_url)

        result = Runner.submit(
            CoreLoopDemoStrategy,
            world=handle.world_ids[0],
            auto_validate=False,
        )
    finally:
        stack.stop()

    assert result.downgraded is True
    assert result.safe_mode is True
    assert result.downgrade_reason in ("decision_unavailable", "stale_decision")
