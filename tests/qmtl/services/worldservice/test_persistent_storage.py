import json

import pytest

from qmtl.services.worldservice.policy_engine import Policy, ThresholdRule
from qmtl.services.worldservice.storage import PersistentStorage


@pytest.mark.asyncio
async def test_persistent_storage_persists_state(tmp_path, fake_redis):
    db_path = tmp_path / "worlds.db"
    storage = await PersistentStorage.create(
        db_dsn=f"sqlite:///{db_path}",
        redis_client=fake_redis,
    )

    world_id = "world-persist"
    try:
        await storage.create_world({"id": world_id, "name": "Primary"})
        policy = Policy(thresholds={"metric": ThresholdRule(metric="alpha", min=0.1)})
        version = await storage.add_policy(world_id, policy)
        await storage.set_default_policy(world_id, version)
        await storage.add_bindings(world_id, ["strategy-1"])
        await storage.set_decisions(world_id, ["strategy-1"])
        await storage.update_activation(
            world_id,
            {
                "strategy_id": "strategy-1",
                "side": "long",
                "active": True,
                "weight": 0.5,
            },
        )
        await storage.set_validation_cache(
            world_id,
            node_id="node-1",
            execution_domain="backtest",
            contract_id="contract",
            dataset_fingerprint="lake:abc",
            code_version="v1",
            resource_policy="default",
            result="ok",
            metrics={"latency": 1.0},
        )
        await storage.upsert_world_node(
            world_id,
            "node-1",
            execution_domain="backtest",
            status="valid",
            last_eval_key="blake3:abc",
            annotations={"note": "persisted"},
        )
        await storage.upsert_edge_override(
            world_id,
            "domain:backtest",
            "domain:live",
            active=False,
            reason="auto:block",
        )
    finally:
        await storage.close()

    storage2 = await PersistentStorage.create(
        db_dsn=f"sqlite:///{db_path}",
        redis_client=fake_redis,
    )
    try:
        world = await storage2.get_world(world_id)
        assert world is not None
        assert world["name"] == "Primary"

        default_policy = await storage2.get_default_policy(world_id)
        assert default_policy is not None
        if hasattr(default_policy, "model_dump"):
            policy_payload = default_policy.model_dump()
        elif hasattr(default_policy, "dict"):
            policy_payload = default_policy.dict()
        else:
            policy_payload = json.loads(json.dumps(default_policy))
        assert policy_payload["thresholds"].keys() == {"metric"}

        decisions = await storage2.get_decisions(world_id)
        assert decisions == ["strategy-1"]

        activation = await storage2.get_activation(
            world_id, strategy_id="strategy-1", side="long"
        )
        assert activation["active"] is True
        assert activation["weight"] == 0.5

        cached = await storage2.get_validation_cache(
            world_id,
            node_id="node-1",
            execution_domain="backtest",
            contract_id="contract",
            dataset_fingerprint="lake:abc",
            code_version="v1",
            resource_policy="default",
        )
        assert cached is not None
        assert cached["result"] == "ok"

        nodes = await storage2.list_world_nodes(world_id)
        assert nodes and nodes[0]["status"] == "valid"

        overrides = await storage2.list_edge_overrides(world_id)
        assert overrides and overrides[0]["reason"] == "auto:block"
    finally:
        await storage2.close()


@pytest.mark.asyncio
async def test_persistent_storage_allocation_state(tmp_path, fake_redis):
    db_path = tmp_path / "alloc.db"
    storage = await PersistentStorage.create(
        db_dsn=f"sqlite:///{db_path}",
        redis_client=fake_redis,
    )
    try:
        await storage.set_world_allocations(
            {"w1": 0.55},
            run_id="alloc-run",
            etag="etag-1",
            strategy_allocations={"w1": {"s1": 0.55}},
        )
        await storage.record_allocation_run(
            "alloc-run",
            "etag-1",
            {
                "plan": {"schema_version": 1, "per_world": {}, "global_deltas": []},
                "request": {"world_alloc_after": {"w1": 0.55}},
            },
            executed=False,
        )
    finally:
        await storage.close()

    storage2 = await PersistentStorage.create(
        db_dsn=f"sqlite:///{db_path}",
        redis_client=fake_redis,
    )
    try:
        state = await storage2.get_world_allocation_state("w1")
        assert state is not None
        assert state.allocation == pytest.approx(0.55)
        assert state.etag == "etag-1"
        run = await storage2.get_allocation_run("alloc-run")
        assert run is not None
        assert run["etag"] == "etag-1"
        assert run["payload"]["plan"]["per_world"] == {}
        assert run["payload"]["plan"]["schema_version"] == 1
        await storage2.mark_allocation_run_executed("alloc-run")
        run_after = await storage2.get_allocation_run("alloc-run")
        assert run_after is not None and run_after["executed"] is True
    finally:
        await storage2.close()
