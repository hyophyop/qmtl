from __future__ import annotations

import json

import pytest

from qmtl.services.dagmanager.diff_service import (
    CrossContextTopicReuseError,
    DiffRequest,
    DiffService,
    NodeInfo,
    NodeRecord,
    StreamSender,
)
from qmtl.services.dagmanager.topic import topic_name
from qmtl.services.dagmanager.monitor import AckStatus

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


def test_stream_ack_window_allows_pipelining(fake_repo, fake_queue):
    class WindowProbeStream(StreamSender):
        def __init__(self) -> None:
            self.chunks_sent = 0
            self.waits = 0
            self.first_wait_at: int | None = None

        def send(self, chunk) -> None:  # type: ignore[override]
            self.chunks_sent += 1

        def wait_for_ack(self) -> AckStatus:  # type: ignore[override]
            if self.first_wait_at is None:
                self.first_wait_at = self.chunks_sent
            self.waits += 1
            return AckStatus.OK

        def ack(self, status: AckStatus = AckStatus.OK) -> None:  # type: ignore[override]
            pass

    stream = WindowProbeStream()
    service = DiffService(fake_repo, fake_queue, stream)

    new_nodes = [
        NodeInfo(
            node_id=f"node-{i}",
            node_type="N",
            code_hash="code",
            schema_hash="schema",
            schema_id="schema-id",
            interval=None,
            period=None,
            tags=[],
        )
        for i in range(1100)
    ]

    service._stream_send({}, "sentinel", "v1", new_nodes, [], crc32=0)

    assert stream.chunks_sent == 11
    assert stream.waits == 11
    assert stream.first_wait_at == 10


def test_stream_ack_window_handles_slow_ack(fake_repo, fake_queue):
    class SlowAckStream(StreamSender):
        def __init__(self) -> None:
            self.chunks_sent = 0
            self.first_wait_at: int | None = None
            self.wait_points: list[int] = []
            self.timeout_calls = 0
            self.resume_calls = 0

        def send(self, chunk) -> None:  # type: ignore[override]
            self.chunks_sent += 1

        def wait_for_ack(self) -> AckStatus:  # type: ignore[override]
            if self.first_wait_at is None:
                self.first_wait_at = self.chunks_sent
            self.wait_points.append(self.chunks_sent)
            if self.timeout_calls < 2:
                self.timeout_calls += 1
                return AckStatus.TIMEOUT
            return AckStatus.OK

        def ack(self, status: AckStatus = AckStatus.OK) -> None:  # type: ignore[override]
            pass

        def resume_from_last_offset(self) -> None:
            self.resume_calls += 1

    stream = SlowAckStream()
    service = DiffService(fake_repo, fake_queue, stream)

    new_nodes = [
        NodeInfo(
            node_id=f"node-{i}",
            node_type="N",
            code_hash="code",
            schema_hash="schema",
            schema_id="schema-id",
            interval=None,
            period=None,
            tags=[],
        )
        for i in range(1500)
    ]

    service._stream_send({}, "sentinel", "v1", new_nodes, [], crc32=0)

    assert stream.chunks_sent == 15
    assert stream.first_wait_at == 10
    assert stream.resume_calls == 2
    assert len(stream.wait_points) == stream.chunks_sent + stream.timeout_calls


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


def test_sentinel_weight_event_emitted_when_version_changes(diff_service):
    def run_diff(version: str):
        request = make_diff_request(
            nodes=[
                dag_node("A", code_hash="c1", schema_hash="s1"),
                {
                    "node_id": "sentinel-node",
                    "node_type": "VersionSentinel",
                    "version": version,
                    "weight": 0.42,
                },
            ]
        )
        diff_service.diff(request)
        return diff_service.consume_weight_events()

    initial_events = run_diff("v1")
    assert [event.sentinel_version for event in initial_events] == ["v1"]
    assert initial_events[0].sentinel_id == "s-sentinel"
    assert initial_events[0].weight == pytest.approx(0.42)

    repeat_events = run_diff("v1")
    assert repeat_events == []

    version_bump_events = run_diff("v2")
    assert [event.sentinel_version for event in version_bump_events] == ["v2"]
    assert version_bump_events[0].weight == pytest.approx(0.42)
