"""Integration-style tests enforcing SSOT boundaries between services."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import networkx as nx
import pytest
from fastapi import HTTPException

from qmtl.foundation.common import compute_node_id, crc32_of_list
from qmtl.services.dagmanager.models import NodeRecord
from qmtl.services.dagmanager.node_repository import MemoryNodeRepository
from qmtl.services.gateway.caches import TTLCache
from qmtl.services.gateway.submission.node_identity import NodeIdentityValidator
from qmtl.services.worldservice.storage import Storage


def _reset_memory_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[MemoryNodeRepository, object, Path]:
    """Return a fresh ``MemoryNodeRepository`` with isolated global state."""

    from qmtl.services.dagmanager import node_repository as module

    monkeypatch.setattr(module, "_GRAPH", nx.DiGraph())
    monkeypatch.setattr(module, "_GRAPH_PATH", None)
    monkeypatch.setattr(module, "_LOADED", False)

    path = tmp_path / "graph.gpickle"
    repo = MemoryNodeRepository(str(path))
    return repo, module, path


def _canonical_node_payload() -> dict[str, object]:
    """Return a canonical node spec suitable for hashing tests."""

    return {
        "node_type": "Indicator",
        "code_hash": "code:v1",
        "config_hash": "cfg:v1",
        "schema_hash": "schema:v1",
        "schema_compat_id": "schema/v1",
        "interval": 60,
        "period": 0,
        "params": {"alpha": 1.5, "beta": 2.5},
        "dependencies": ["blake3:upstream"],
        "tags": ["core"],
    }


def _make_record(node_id: str) -> NodeRecord:
    payload = _canonical_node_payload()
    return NodeRecord(
        node_id=node_id,
        node_type=str(payload["node_type"]),
        code_hash=str(payload["code_hash"]),
        schema_hash=str(payload["schema_hash"]),
        schema_id=str(payload["schema_compat_id"]),
        interval=int(payload["interval"]),
        period=int(payload["period"]),
        tags=list(payload["tags"]),
        bucket=None,
        is_global=True,
        topic="indicator.core.v1",
    )


def _collect_missing(repo: MemoryNodeRepository, node_ids: Iterable[str]) -> set[str]:
    existing = repo.get_nodes(node_ids)
    return set(node_ids) - set(existing)


def test_gsg_immutability_across_restarts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo, module, graph_path = _reset_memory_repo(tmp_path, monkeypatch)

    payload = _canonical_node_payload()
    node_id = compute_node_id(payload)
    dag = {"nodes": [{**payload, "node_id": node_id}]}
    checksum = crc32_of_list([node_id])

    validator = NodeIdentityValidator()
    report = validator.validate(dag, checksum)
    assert report.is_valid

    mutated = dict(dag["nodes"][0])
    mutated["code_hash"] = "code:v2"
    with pytest.raises(HTTPException) as excinfo:
        validator.validate({"nodes": [mutated]}, checksum)
    detail = excinfo.value.detail
    assert detail.get("code") == "E_NODE_ID_MISMATCH"
    assert detail["node_id_mismatch"][0]["node_id"] == node_id

    record = _make_record(node_id)
    repo.add_node(record)
    original = repo.get_nodes([node_id])[node_id]
    assert original.code_hash == record.code_hash

    module._save_graph()  # type: ignore[attr-defined]
    module._GRAPH = nx.DiGraph()  # type: ignore[attr-defined]
    module._LOADED = False  # type: ignore[attr-defined]

    restarted = MemoryNodeRepository(str(graph_path))
    restored = restarted.get_nodes([node_id])[node_id]
    assert restored == original


@pytest.mark.asyncio
async def test_wvg_world_isolation_strict() -> None:
    store = Storage()
    context = {
        "node_id": "blake3:gsg-node",
        "execution_domain": "live",
        "contract_id": "contract-a",
        "dataset_fingerprint": "lake:blake3:data-a",
        "code_version": "rev1",
        "resource_policy": "standard",
    }

    await store.set_validation_cache(
        "world-a",
        **context,
        result="allow",
        metrics={"score": 0.9},
        timestamp="2025-10-09T00:00:00Z",
    )

    cached = await store.get_validation_cache("world-a", **context)
    assert cached is not None

    other = await store.get_validation_cache("world-b", **context)
    assert other is None

    await store.set_decisions("world-a", ["strategy-1"])
    await store.set_decisions("world-b", ["strategy-2"])
    assert await store.get_decisions("world-a") == ["strategy-1"]
    assert await store.get_decisions("world-b") == ["strategy-2"]

    await store.update_activation(
        "world-a",
        {"strategy_id": "strategy-1", "side": "long", "active": True},
    )
    activation_a = await store.get_activation("world-a")
    activation_b = await store.get_activation("world-b")
    assert activation_a["state"]["strategy-1"]["long"]["active"] is True
    assert activation_b == {"version": 0, "state": {}}

    await store.upsert_edge_override(
        "world-a",
        "node-src",
        "node-dst",
        active=True,
        reason="manual",
    )
    assert await store.list_edge_overrides("world-a") != []
    assert await store.list_edge_overrides("world-b") == []


@pytest.mark.asyncio
async def test_gateway_cache_non_ssot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo, module, _ = _reset_memory_repo(tmp_path, monkeypatch)
    record = _make_record("blake3:cache-node")
    repo.add_node(record)

    store = Storage()
    context = {
        "node_id": record.node_id,
        "execution_domain": "live",
        "contract_id": "contract-a",
        "dataset_fingerprint": "lake:blake3:data-a",
        "code_version": "rev1",
        "resource_policy": "standard",
    }
    await store.set_validation_cache(
        "world-cache",
        **context,
        result="allow",
        metrics={"score": 1.0},
        timestamp="2025-10-09T00:00:00Z",
    )

    cache = TTLCache()
    cache.set("world-cache:queue", {"queue": "topic", "global": False}, ttl=60)
    cache.invalidate("world-cache:queue")

    corrupted_entry = {"queue": "corrupt", "global": True}
    cache.set("world-cache:queue", corrupted_entry, ttl=60)
    cache.clear()

    stored = repo.get_nodes([record.node_id])[record.node_id]
    assert stored.topic == record.topic

    cached = await store.get_validation_cache("world-cache", **context)
    assert cached is not None
    assert cached.result == "allow"


@pytest.mark.asyncio
async def test_cross_service_consistency_detection(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo, module, _ = _reset_memory_repo(tmp_path, monkeypatch)
    record = _make_record("blake3:consistency-node")
    repo.add_node(record)

    store = Storage()
    await store.create_world({"id": "world-consistency"})
    await store.upsert_world_node(
        "world-consistency",
        record.node_id,
        execution_domain="live",
        status="running",
    )

    world_nodes = await store.list_world_nodes("world-consistency", execution_domain="live")
    node_ids = [entry["node_id"] for entry in world_nodes]
    assert _collect_missing(repo, node_ids) == set()

    module._GRAPH = nx.DiGraph()  # type: ignore[attr-defined]
    module._LOADED = True  # type: ignore[attr-defined]
    assert _collect_missing(repo, node_ids) == {record.node_id}

    repo.add_node(record)
    assert _collect_missing(repo, node_ids) == set()


@pytest.mark.asyncio
async def test_evalkey_reproducibility() -> None:
    store = Storage()
    context = {
        "node_id": "blake3:eval-node",
        "execution_domain": "live",
        "contract_id": "contract-a",
        "dataset_fingerprint": "lake:blake3:data-a",
        "code_version": "rev1",
        "resource_policy": "standard",
    }

    entry1 = await store.set_validation_cache(
        "world-eval",
        **context,
        result="allow",
        metrics={"score": 0.9},
        timestamp="2025-10-09T00:00:00Z",
    )
    entry2 = await store.set_validation_cache(
        "world-eval",
        **context,
        result="allow",
        metrics={"score": 0.95},
        timestamp="2025-10-09T00:01:00Z",
    )
    assert entry1.eval_key == entry2.eval_key

    cached = await store.get_validation_cache("world-eval", **context)
    assert cached is not None
    assert cached.eval_key == entry1.eval_key

    entry3 = await store.set_validation_cache(
        "world-eval",
        **{**context, "code_version": "rev2"},
        result="allow",
        metrics={"score": 0.5},
        timestamp="2025-10-09T00:02:00Z",
    )
    assert entry3.eval_key != entry1.eval_key
