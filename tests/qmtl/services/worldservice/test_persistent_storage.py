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
