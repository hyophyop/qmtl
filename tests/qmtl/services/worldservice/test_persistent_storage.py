import json
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from qmtl.services.worldservice.policy_engine import Policy, ThresholdRule
from qmtl.services.worldservice.storage import PersistentStorage
from qmtl.services.worldservice.storage.repositories import (
    PersistentActivationRepository,
    PersistentBindingRepository,
    PersistentPolicyRepository,
    PersistentWorldRepository,
    _REASON_UNSET,
)


@pytest_asyncio.fixture
async def persistent_storage(tmp_path, fake_redis):
    db_path = tmp_path / "worlds.db"
    storage = await PersistentStorage.create(
        db_dsn=f"sqlite:///{db_path}",
        redis_client=fake_redis,
    )
    try:
        yield storage
    finally:
        await storage.close()


@pytest.mark.asyncio
async def test_persistent_world_repository_crud(persistent_storage):
    repo: PersistentWorldRepository = persistent_storage._world_repo
    world = {"id": "world-1", "name": "Primary", "contract_id": "cid"}
    await repo.create(world)
    stored = await repo.get("world-1")
    assert stored is not None and stored["name"] == "Primary"

    await repo.update("world-1", {"name": "Updated"})
    updated = await repo.get("world-1")
    assert updated is not None and updated["name"] == "Updated"

    rows = await persistent_storage._driver.fetchall(
        "SELECT entry FROM audit_logs WHERE world_id = ? ORDER BY id",
        "world-1",
    )
    assert [json.loads(row[0])["event"] for row in rows] == [
        "world_created",
        "world_updated",
    ]

    await repo.delete("world-1")
    assert await repo.get("world-1") is None


@pytest.mark.asyncio
async def test_persistent_policy_repository_roundtrip(persistent_storage):
    world_repo: PersistentWorldRepository = persistent_storage._world_repo
    await world_repo.create({"id": "world-policy"})
    repo: PersistentPolicyRepository = persistent_storage._policy_repo
    policy = Policy(thresholds={"metric": ThresholdRule(metric="alpha", min=0.1)})

    version = await repo.add("world-policy", policy)
    assert version == 1
    listed = await repo.list_versions("world-policy")
    assert listed == [{"version": 1}]

    fetched = await repo.get("world-policy", 1)
    assert fetched is not None
    assert fetched.thresholds["metric"].metric == "alpha"

    await repo.set_default("world-policy", 1)
    default_version = await repo.default_version("world-policy")
    assert default_version == 1
    assert await repo.get_default("world-policy") is not None

    await repo.delete_all("world-policy")
    assert await repo.list_versions("world-policy") == []


@pytest.mark.asyncio
async def test_persistent_binding_repository_behaviour(persistent_storage):
    world_repo: PersistentWorldRepository = persistent_storage._world_repo
    await world_repo.create({"id": "world-binding"})
    repo: PersistentBindingRepository = persistent_storage._binding_repo

    await repo.add("world-binding", ["strategy-1", "strategy-2"])
    bindings = await repo.list("world-binding")
    assert bindings == ["strategy-1", "strategy-2"]

    await repo.set_decisions("world-binding", ["strategy-2"])
    decisions = await repo.get_decisions("world-binding")
    assert decisions == ["strategy-2"]

    await repo.clear("world-binding")
    assert await repo.list("world-binding") == []
    assert await repo.get_decisions("world-binding") == []


@pytest.mark.asyncio
async def test_persistent_activation_repository(persistent_storage):
    repo: PersistentActivationRepository = persistent_storage._activation_repo
    state = await repo.get("world-activation")
    assert state == {"version": 0, "state": {}}

    version, entry = await repo.update(
        "world-activation",
        {
            "strategy_id": "strategy-1",
            "side": "long",
            "active": True,
            "weight": 0.75,
        },
    )
    assert version == 1
    assert entry["active"] is True
    snapshot = await repo.snapshot("world-activation")
    await repo.restore("world-activation", snapshot)
    await repo.clear("world-activation")
    assert await repo.get("world-activation") == {"version": 0, "state": {}}


@pytest.mark.asyncio
async def test_persistent_storage_facade_delegates(persistent_storage):
    storage = persistent_storage
    storage._world_repo = AsyncMock()
    storage._binding_repo = AsyncMock()
    storage._policy_repo = AsyncMock()
    storage._activation_repo = AsyncMock()
    storage.ensure_default_edge_overrides = AsyncMock()
    storage.invalidate_validation_cache = AsyncMock()

    await storage.create_world({"id": "delegated"})
    storage._world_repo.create.assert_awaited_once_with({"id": "delegated"})
    storage.ensure_default_edge_overrides.assert_awaited_once_with("delegated")

    policy = Policy(thresholds={})
    await storage.add_policy("delegated", policy)
    storage._policy_repo.add.assert_awaited_once_with("delegated", policy)
    storage.invalidate_validation_cache.assert_awaited_once_with("delegated")

    await storage.add_bindings("delegated", ["s1"])
    storage._binding_repo.add.assert_awaited_once_with("delegated", ["s1"])

    await storage.get_activation("delegated")
    storage._activation_repo.get.assert_awaited_once_with(
        "delegated", strategy_id=None, side=None
    )


@pytest.mark.asyncio
async def test_persistent_storage_validation_cache_and_invalidation(
    persistent_storage,
):
    world_id = "world-validation"
    await persistent_storage.create_world({"id": world_id})

    recorded = await persistent_storage.set_validation_cache(
        world_id,
        node_id="node-1",
        execution_domain="Live",
        contract_id="cid",
        dataset_fingerprint="dfp",
        code_version="v1",
        resource_policy="p1",
        result="pass",
        metrics={"latency_ms": 10},
    )
    assert recorded["execution_domain"] == "live"
    fetched = await persistent_storage.get_validation_cache(
        world_id,
        node_id="node-1",
        execution_domain="live",
        contract_id="cid",
        dataset_fingerprint="dfp",
        code_version="v1",
        resource_policy="p1",
    )
    assert fetched is not None
    assert fetched["result"] == "pass"

    await persistent_storage.set_validation_cache(
        world_id,
        node_id="node-2",
        execution_domain="backtest",
        contract_id="cid",
        dataset_fingerprint="dfp",
        code_version="v1",
        resource_policy="p1",
        result="pass",
        metrics={},
    )
    await persistent_storage.invalidate_validation_cache(
        world_id, execution_domain="LIVE"
    )

    cleared = await persistent_storage.get_validation_cache(
        world_id,
        node_id="node-1",
        execution_domain="live",
        contract_id="cid",
        dataset_fingerprint="dfp",
        code_version="v1",
        resource_policy="p1",
    )
    assert cleared is None
    remaining = await persistent_storage.get_validation_cache(
        world_id,
        node_id="node-2",
        execution_domain="backtest",
        contract_id="cid",
        dataset_fingerprint="dfp",
        code_version="v1",
        resource_policy="p1",
    )
    assert remaining is not None


@pytest.mark.asyncio
async def test_persistent_storage_edge_overrides_audit_and_reason(persistent_storage):
    world_id = "world-edge"
    await persistent_storage.create_world({"id": world_id})

    override = await persistent_storage.upsert_edge_override(
        world_id,
        "src",
        "dst",
        active=True,
        reason="initial",
    )
    assert override["active"] is True

    updated = await persistent_storage.upsert_edge_override(
        world_id,
        "src",
        "dst",
        active=False,
        reason=_REASON_UNSET,
    )
    assert updated["reason"] == "initial"

    overrides = await persistent_storage.list_edge_overrides(world_id)
    assert any(ovr["src_node_id"] == "src" and ovr["dst_node_id"] == "dst" for ovr in overrides)

    audit_events = [entry["event"] for entry in await persistent_storage.get_audit(world_id)]
    assert audit_events[-1] == "edge_override_upserted"


@pytest.mark.asyncio
async def test_allocation_runs_and_world_allocations(persistent_storage):
    world_id = "world-allocation"
    await persistent_storage.create_world({"id": world_id})

    payload = {"allocations": {"a": 1}}
    await persistent_storage.record_allocation_run("run-1", "etag-1", payload)
    run = await persistent_storage.get_allocation_run("run-1")
    assert run is not None and run["executed"] is False

    await persistent_storage.mark_allocation_run_executed("run-1")
    executed = await persistent_storage.get_allocation_run("run-1")
    assert executed is not None and executed["executed"] is True

    await persistent_storage.set_world_allocations(
        {world_id: 0.42},
        run_id="run-1",
        etag="etag-2",
        strategy_allocations={world_id: {"s1": 0.2}},
    )
    state = await persistent_storage.get_world_allocation_state(world_id)
    assert state is not None
    assert state.allocation == 0.42
    assert state.run_id == "run-1"
    assert state.etag == "etag-2"
    assert state.strategy_alloc_total == {"s1": 0.2}


@pytest.mark.asyncio
async def test_update_world_invalidates_validation_cache(persistent_storage):
    world_id = "world-update"
    await persistent_storage.create_world({"id": world_id, "contract_id": "cid-1"})

    await persistent_storage.set_validation_cache(
        world_id,
        node_id="node-1",
        execution_domain="LIVE",
        contract_id="cid-1",
        dataset_fingerprint="dfp",
        code_version="v1",
        resource_policy="p1",
        result="pass",
        metrics={},
    )
    assert await persistent_storage.get_validation_cache(
        world_id,
        node_id="node-1",
        execution_domain="live",
        contract_id="cid-1",
        dataset_fingerprint="dfp",
        code_version="v1",
        resource_policy="p1",
    ) is not None

    await persistent_storage.update_world(world_id, {"contract_id": "cid-2"})

    assert await persistent_storage.get_validation_cache(
        world_id,
        node_id="node-1",
        execution_domain="live",
        contract_id="cid-1",
        dataset_fingerprint="dfp",
        code_version="v1",
        resource_policy="p1",
    ) is None
    audit_events = [entry["event"] for entry in await persistent_storage.get_audit(world_id)]
    assert "validation_cache_invalidated" in audit_events


@pytest.mark.asyncio
async def test_validation_cache_invalidation_scoped_by_node_and_domain(persistent_storage):
    world_id = "world-cache-scope"
    await persistent_storage.create_world({"id": world_id})

    await persistent_storage.set_validation_cache(
        world_id,
        node_id="node-a",
        execution_domain="live",
        contract_id="cid",
        dataset_fingerprint="dfp",
        code_version="v1",
        resource_policy="p1",
        result="pass",
        metrics={},
    )
    await persistent_storage.set_validation_cache(
        world_id,
        node_id="node-a",
        execution_domain="backtest",
        contract_id="cid",
        dataset_fingerprint="dfp",
        code_version="v1",
        resource_policy="p1",
        result="pass",
        metrics={},
    )

    await persistent_storage.invalidate_validation_cache(
        world_id, node_id="node-a", execution_domain="LIVE"
    )

    assert await persistent_storage.get_validation_cache(
        world_id,
        node_id="node-a",
        execution_domain="live",
        contract_id="cid",
        dataset_fingerprint="dfp",
        code_version="v1",
        resource_policy="p1",
    ) is None
    remaining = await persistent_storage.get_validation_cache(
        world_id,
        node_id="node-a",
        execution_domain="backtest",
        contract_id="cid",
        dataset_fingerprint="dfp",
        code_version="v1",
        resource_policy="p1",
    )
    assert remaining is not None and remaining["execution_domain"] == "backtest"
    last_audit = (await persistent_storage.get_audit(world_id))[-1]
    assert last_audit == {
        "event": "validation_cache_invalidated",
        "node_id": "node-a",
        "execution_domain": "live",
    }


@pytest.mark.asyncio
async def test_world_node_crud_and_normalization(persistent_storage):
    world_id = "world-nodes"
    await persistent_storage.create_world({"id": world_id})

    upserted = await persistent_storage.upsert_world_node(
        world_id,
        "node-1",
        execution_domain="LIVE",
        status="RUNNING",
        annotations={"note": True},
    )
    assert upserted == {
        "world_id": world_id,
        "node_id": "node-1",
        "execution_domain": "live",
        "status": "running",
        "last_eval_key": None,
        "annotations": {"note": True},
    }

    await persistent_storage.upsert_world_node(
        world_id,
        "node-1",
        execution_domain="shadow",
        status="paused",
        last_eval_key="eval-2",
    )

    all_nodes = await persistent_storage.list_world_nodes(world_id)
    assert {entry["execution_domain"] for entry in all_nodes} == {"live", "shadow"}

    live_node = await persistent_storage.get_world_node(
        world_id, "node-1", execution_domain="live"
    )
    assert live_node is not None and live_node["status"] == "running"

    await persistent_storage.delete_world_node(world_id, "node-1", execution_domain="shadow")
    assert [entry["execution_domain"] for entry in await persistent_storage.list_world_nodes(world_id)] == ["live"]

    await persistent_storage.delete_world_node(world_id, "node-1")
    assert await persistent_storage.list_world_nodes(world_id) == []


@pytest.mark.asyncio
async def test_history_metadata_ordering_and_latest_selection(persistent_storage):
    world_id = "world-history"
    await persistent_storage.create_world({"id": world_id})

    await persistent_storage.upsert_history_metadata(
        world_id,
        "strategy-a",
        {"dataset_fingerprint": "fp1", "as_of": "2024-01-01T00:00:00Z", "updated_at": "2024-01-02T00:00:00Z"},
    )
    await persistent_storage.upsert_history_metadata(
        world_id,
        "strategy-b",
        {"dataset_fingerprint": "fp2", "updated_at": "2024-04-01T00:00:00Z"},
    )
    await persistent_storage.upsert_history_metadata(
        world_id,
        "strategy-c",
        {"dataset_fingerprint": "fp3", "as_of": "2024-02-01T00:00:00Z", "updated_at": "2024-02-02T00:00:00Z"},
    )

    listed = await persistent_storage.list_history_metadata(world_id)
    assert {entry["strategy_id"] for entry in listed} == {"strategy-a", "strategy-b", "strategy-c"}

    latest = await persistent_storage.latest_history_metadata(world_id)
    assert latest is not None
    assert latest["strategy_id"] == "strategy-c"
    assert latest["as_of"] == "2024-02-01T00:00:00Z"
