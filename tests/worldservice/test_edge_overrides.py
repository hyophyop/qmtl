from __future__ import annotations

import pytest

from qmtl.worldservice.edge_overrides import EdgeOverrideManager
from qmtl.worldservice.policy import GatingPolicy


class _StubStore:
    def __init__(self) -> None:
        self.overrides: dict[tuple[str, str, str], dict | None] = {}

    async def get_edge_override(self, world_id: str, src: str, dst: str):
        return self.overrides.get((world_id, src, dst))

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
        self.overrides[(world_id, src, dst)] = entry
        return entry

    async def delete_edge_override(self, world_id: str, src: str, dst: str) -> None:
        self.overrides.pop((world_id, src, dst), None)


def _policy() -> GatingPolicy:
    return GatingPolicy.model_validate(
        {
            "dataset_fingerprint": "demo",
            "share_policy": "feature-artifacts-only",
            "snapshot": {"strategy_plane": "cow", "feature_plane": "readonly"},
            "edges": {
                "pre_promotion": {"disable_edges_to": ["dryrun", "live"]},
                "post_promotion": {"enable_edges_to": "live"},
            },
            "observability": {"slo": {"cross_context_cache_hit": 0}},
        }
    )


@pytest.mark.asyncio
async def test_edge_override_manager_plan_and_restore() -> None:
    store = _StubStore()
    manager = EdgeOverrideManager(store, "world")
    plan = EdgeOverrideManager.plan_for(_policy())

    assert plan.pre_disable == ["dryrun", "live"]
    assert plan.post_enable == ["live"]

    await manager.apply_pre_promotion(plan.pre_disable, "run-1")
    await manager.apply_post_promotion(plan.post_enable, "run-1")

    key = ("world", "domain:backtest", "domain:live")
    assert store.overrides[key]["reason"] == "post_promotion_enable:run-1"

    await manager.restore()
    assert key not in store.overrides


def test_edge_override_manager_rejects_unknown_domain() -> None:
    policy = _policy().model_copy()
    policy.edges.post_promotion.enable_edges_to = ["unknown"]
    with pytest.raises(ValueError):
        EdgeOverrideManager.plan_for(policy)
