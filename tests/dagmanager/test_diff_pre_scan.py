from __future__ import annotations

import json

import pytest

from qmtl.services.dagmanager.diff_service import DiffRequest

from .diff_helpers import build_dag, dag_node

pytestmark = [
    pytest.mark.filterwarnings("ignore::pytest.PytestUnraisableExceptionWarning"),
    pytest.mark.filterwarnings("ignore:unclosed <socket.socket[^>]*>"),
    pytest.mark.filterwarnings("ignore:unclosed event loop"),
]


def test_pre_scan_and_db_fetch_topo_order(diff_service, fake_repo, make_request):
    request = make_request(
        nodes=[
            dag_node("B", code_hash="c2", schema_hash="s2", inputs=["A"]),
            dag_node("A", code_hash="c1", schema_hash="s1"),
        ]
    )

    diff_service.diff(request)

    assert fake_repo.fetched[0] == ["A", "B"]


def test_pre_scan_and_db_fetch(diff_service, fake_repo, make_request):
    request = make_request(
        nodes=[
            dag_node("A", code_hash="c1", schema_hash="s1"),
            dag_node("B", code_hash="c2", schema_hash="s2"),
        ]
    )

    diff_service.diff(request)

    assert fake_repo.fetched[0] == ["A", "B"]


def test_pre_scan_uses_custom_json_loader(monkeypatch, diff_service):
    calls: list[str] = []

    def fake_loads(data: str):
        calls.append(data)
        return {"nodes": []}

    import qmtl.services.dagmanager.diff_service as mod

    monkeypatch.setattr(mod, "_json_loads", fake_loads)

    diff_service.diff(DiffRequest(strategy_id="s", dag_json="{}"))

    assert calls == ["{}"]


def test_diff_with_sdk_nodes(diff_service):
    """End-to-end check with nodes serialized by the SDK."""
    from qmtl.runtime.sdk import ProcessingNode, Strategy, StreamInput

    class _S(Strategy):
        def setup(self):
            src = StreamInput(interval="1s", period=1)
            node = ProcessingNode(
                input=src,
                compute_fn=lambda x: x,
                name="out",
                interval="1s",
                period=1,
            )
            self.add_nodes([src, node])

    strategy = _S()
    strategy.setup()

    request = DiffRequest(strategy_id="sid", dag_json=json.dumps(strategy.serialize()))

    chunk = diff_service.diff(request)

    assert chunk.queue_map


def test_build_dag_helper_round_trip():
    nodes = [
        dag_node("A", code_hash="c1", schema_hash="s1"),
        dag_node("B", code_hash="c2", schema_hash="s2"),
    ]
    dag_json = build_dag(nodes)

    parsed = json.loads(dag_json)

    assert parsed["nodes"] == nodes
