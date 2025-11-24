from __future__ import annotations

import importlib
import json
from pathlib import Path

import asyncio
import networkx as nx
import pytest

from qmtl.services.dagmanager import node_repository
from qmtl.services.dagmanager.models import NodeRecord


@pytest.fixture(autouse=True)
def reset_repo_module():
    importlib.reload(node_repository)
    yield
    importlib.reload(node_repository)


@pytest.fixture(autouse=True, scope="module")
def ensure_event_loop():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        yield
    finally:
        loop.close()
        # Reset the event loop policy so subsequent async tests get a fresh loop.
        asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())


def test_load_graph_falls_back_to_json(tmp_path: Path):
    graph = nx.DiGraph()
    graph.add_node(
        "n1",
        type="compute",
        node_type="N",
        code_hash="c1",
        schema_hash="s1",
        schema_id="id1",
        interval=60,
        period=None,
        tags=["t1"],
        bucket=None,
        topic="q1",
        **{"global": False},
    )
    data = nx.node_link_data(graph, edges="edges")
    graph_path = tmp_path / "graph.gpickle"
    graph_path.write_text(json.dumps(data))

    repo = node_repository.MemoryNodeRepository(str(graph_path))

    nodes = repo.get_nodes(["n1"])
    assert nodes["n1"].topic == "q1"
    assert nodes["n1"].node_type == "N"


def test_load_graph_recovers_from_corruption(tmp_path: Path):
    graph_path = tmp_path / "graph.gpickle"
    graph_path.write_text("not a graph")

    repo = node_repository.MemoryNodeRepository(str(graph_path))

    assert repo.get_nodes(["missing"]) == {}


def test_save_graph_falls_back_to_node_link(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    graph_path = tmp_path / "graph.gpickle"
    repo = node_repository.MemoryNodeRepository(str(graph_path))
    repo.add_node(
        NodeRecord(
            node_id="n1",
            node_type="N",
            code_hash="c1",
            schema_hash="s1",
            schema_id="id1",
            interval=60,
            period=None,
            tags=["t1"],
            bucket=None,
            is_global=False,
            topic="q1",
        )
    )

    def boom(*_args, **_kwargs):
        raise IOError("boom")

    monkeypatch.setattr(nx, "write_gpickle", boom, raising=False)

    node_repository._save_graph()

    persisted = json.loads(graph_path.read_text())
    assert persisted["nodes"][0]["id"] == "n1"
    assert persisted["nodes"][0]["topic"] == "q1"


def test_get_nodes_filters_non_compute(tmp_path: Path):
    repo = node_repository.MemoryNodeRepository(str(tmp_path / "graph.gpickle"))
    repo.add_node(
        NodeRecord(
            node_id="compute",
            node_type="N",
            code_hash="c1",
            schema_hash="s1",
            schema_id="id1",
            interval=30,
            period=None,
            tags=["t1"],
            bucket=None,
            is_global=True,
            topic="q1",
        )
    )
    repo.insert_sentinel("sentinel", ["compute"], version="v1")

    records = repo.get_nodes(["compute", "sentinel", "missing"])

    assert set(records) == {"compute"}
    assert records["compute"].is_global is True


def test_buffering_state_transitions(tmp_path: Path):
    repo = node_repository.MemoryNodeRepository(str(tmp_path / "graph.gpickle"))
    repo.add_node(
        NodeRecord(
            node_id="n1",
            node_type="N",
            code_hash="c1",
            schema_hash="s1",
            schema_id="id1",
            interval=60,
            period=None,
            tags=["t1"],
            bucket=None,
            is_global=False,
            topic="q1",
        )
    )

    repo.mark_buffering("n1", compute_key="k1", timestamp_ms=20)

    assert repo.get_buffering_nodes(older_than_ms=15) == []
    assert repo.get_buffering_nodes(older_than_ms=25, compute_key="k1") == ["n1"]

    repo.clear_buffering("n1", compute_key="k1")
    assert repo.get_buffering_nodes(older_than_ms=25, compute_key="k1") == []

    repo.mark_buffering("n1", timestamp_ms=10)
    repo.mark_buffering("n1", compute_key="k1", timestamp_ms=20)
    repo.clear_buffering("n1")
    assert repo.get_buffering_nodes(older_than_ms=15) == []
