from __future__ import annotations

import json

import pytest

from qmtl.services.dagmanager.diff_service import CrossContextTopicReuseError

from qmtl.services.dagmanager.diff_service import DiffRequest, DiffService, NodeRecord
from qmtl.services.dagmanager.topic import topic_name

from .diff_fakes import FakeStream, TimeoutOnceStream
from .diff_helpers import dag_node, make_diff_request, partition_with_context

pytestmark = [
    pytest.mark.filterwarnings("ignore::pytest.PytestUnraisableExceptionWarning"),
    pytest.mark.filterwarnings("ignore:unclosed <socket.socket[^>]*>"),
    pytest.mark.filterwarnings("ignore:unclosed event loop"),
]


def test_hash_compare_and_queue_upsert(diff_service, fake_repo, fake_queue):
    fake_repo.records["A"] = NodeRecord(
        "A",
        "N",
        "c1",
        "s1",
        "id1",
        None,
        None,
        [],
        None,
        False,
        topic_name("asset", "N", "c1", "v1"),
    )

    request = make_diff_request(
        nodes=[
            dag_node("A", code_hash="c1", schema_hash="s1"),
            dag_node("B", code_hash="c2", schema_hash="s2"),
        ]
    )

    chunk = diff_service.diff(request)

    expected_a = topic_name("asset", "N", "c1", "v1")
    expected_b = topic_name("asset", "N", "c2", "v1")

    assert chunk.queue_map[partition_with_context("A", None, None)] == expected_a
    assert chunk.queue_map[partition_with_context("B", None, None)] == expected_b
    assert fake_queue.calls == [("asset", "N", "c2", "v1", False, None)]


def test_compute_key_isolation_and_metrics(diff_service, fake_repo, fake_queue, diff_metrics):
    fake_repo.records["A"] = NodeRecord(
        "A",
        "N",
        "c1",
        "s1",
        "id1",
        None,
        None,
        [],
        None,
        False,
        topic_name("asset", "N", "c1", "v1"),
    )

    dag_live = json.dumps(
        {
            "nodes": [
                dag_node("A", code_hash="c1", schema_hash="s1"),
            ],
            "meta": {"compute_context": {"world_id": "w1", "execution_domain": "live"}},
        }
    )

    dag_backtest = json.dumps(
        {
            "nodes": [
                dag_node("A", code_hash="c1", schema_hash="s1"),
            ],
            "meta": {"compute_context": {"world_id": "w2", "execution_domain": "backtest"}},
        }
    )

    diff_service.diff(DiffRequest(strategy_id="s", dag_json=dag_live))
    with pytest.raises(CrossContextTopicReuseError) as exc:
        diff_service.diff(DiffRequest(strategy_id="s", dag_json=dag_backtest))

    assert "A" in str(exc.value)
    assert len(fake_queue.calls) == 1
    key = ("A", "w2", "backtest", "__unset__", "__unset__")
    assert diff_metrics.cross_context_cache_hit_total._vals.get(key) == 1  # type: ignore[attr-defined]
    violation_key = ("A", "w2", "backtest")
    assert (
        diff_metrics.cross_context_cache_violation_total._vals.get(violation_key) == 1
    )  # type: ignore[attr-defined]


def test_sentinel_insert_and_stream(diff_service, fake_repo, fake_stream):
    request = make_diff_request(
        strategy_id="strategy",
        nodes=[dag_node("A", code_hash="c1", schema_hash="s1")],
    )

    chunk = diff_service.diff(request)

    assert fake_repo.sentinels == [("strategy-sentinel", ["A"], "v1")]
    assert fake_stream.chunks[0] == chunk
    assert chunk.sentinel_id == "strategy-sentinel"


def test_version_extracted_from_sentinel_node(diff_service, fake_repo, fake_queue):
    request = make_diff_request(
        strategy_id="sid",
        nodes=[
            dag_node("A", code_hash="c1", schema_hash="s1", tags=["btc"]),
            {
                "node_id": "sentinel-node",
                "node_type": "VersionSentinel",
                "version": "release-2025.09",
            },
        ],
    )

    chunk = diff_service.diff(request)

    assert fake_queue.calls[-1][3] == "release-2025.09"
    assert chunk.version == "release-2025.09"
    assert fake_repo.sentinels[-1] == (
        "sid-sentinel",
        ["A"],
        "release-2025.09",
    )


def test_stream_resumes_after_timeout(fake_repo, fake_queue):
    stream = TimeoutOnceStream()
    service = DiffService(fake_repo, fake_queue, stream)
    request = make_diff_request(nodes=[dag_node("A", code_hash="c1", schema_hash="s1")])

    service.diff(request)

    assert stream.resumes == 1
    assert stream.waits == 2


def test_stream_chunking_and_ack(fake_repo, fake_queue):
    stream = FakeStream()

    service = DiffService(fake_repo, fake_queue, stream)
    nodes = [
        dag_node(str(i), code_hash="c", schema_hash="s")
        for i in range(250)
    ]
    request = make_diff_request(nodes=nodes)

    service.diff(request)

    assert len(stream.chunks) == 3
    assert stream.waits == 3


def test_sentinel_gap_metric_increment(diff_service, fake_repo, diff_metrics):
    fake_repo.records["A"] = NodeRecord(
        "A",
        "N",
        "c1",
        "s1",
        "id1",
        None,
        None,
        [],
        None,
        topic_name("asset", "N", "c1", "v1"),
    )

    request = make_diff_request(
        nodes=[dag_node("A", code_hash="c1", schema_hash="s1")],
    )

    diff_service.diff(request)

    assert diff_metrics.sentinel_gap_count._value.get() == 1  # type: ignore[attr-defined]
