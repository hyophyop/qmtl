from datetime import datetime, timedelta, UTC

import pytest

from qmtl.services.dagmanager.diff_service import (
    DiffService,
    DiffRequest,
    NodeRepository,
    QueueManager,
    StreamSender,
)
from qmtl.services.dagmanager.topic import topic_name
from qmtl.services.dagmanager.garbage_collector import GarbageCollector, QueueInfo
import httpx
import time
from qmtl.foundation.common.metrics_factory import get_mapping_store, get_metric_value
from qmtl.services.dagmanager import metrics
from qmtl.services.dagmanager.monitor import AckStatus


class FakeRepo(NodeRepository):
    def get_nodes(self, node_ids):
        return {}

    def insert_sentinel(self, sentinel_id, node_ids, version):
        pass

    def get_queues_by_tag(self, tags, interval, match_mode="any"):
        return []

    def mark_buffering(self, node_id, *, compute_key=None, timestamp_ms=None):
        pass

    def clear_buffering(self, node_id, *, compute_key=None):
        pass

    def get_buffering_nodes(self, older_than_ms, *, compute_key=None):
        return []


class FakeQueue(QueueManager):
    def upsert(
        self,
        asset,
        node_type,
        code_hash,
        version,
        *,
        dry_run=False,
        namespace=None,
    ):
        return topic_name(
            asset,
            node_type,
            code_hash,
            version,
            dry_run=dry_run,
            namespace=namespace,
        )


class FailingQueue(QueueManager):
    def upsert(
        self,
        asset,
        node_type,
        code_hash,
        version,
        *,
        dry_run=False,
        namespace=None,
    ):
        raise RuntimeError("fail")


class FakeStream(StreamSender):
    def send(self, chunk):
        pass

    def wait_for_ack(self) -> AckStatus:
        return AckStatus.OK

    def ack(self, status: AckStatus = AckStatus.OK):
        pass


class DummyMetrics:
    def __init__(self, val: float = 0) -> None:
        self.val = val

    def messages_in_per_sec(self) -> float:
        return self.val


def _make_dag():
    return (
        '{"nodes": ['
        '{"node_id": "A", "node_type": "N", "code_hash": "c", "config_hash": "cfg", '
        '"schema_hash": "s", "schema_compat_id": "s-major", "params": {}, "dependencies": []}'
        ']}'
    )


def test_metrics_exposed():
    metrics.reset_metrics()
    metrics.diff_duration_ms_p95.set(10)
    metrics.queue_create_error_total.inc()
    metrics.orphan_queue_total.set(2)
    metrics.sentinel_gap_count.inc()
    metrics.set_active_version_weight("v1", 0.4)

    data = metrics.collect_metrics()
    assert "diff_duration_ms_p95" in data
    assert "queue_create_error_total" in data
    assert "orphan_queue_total" in data
    assert "sentinel_gap_count" in data
    assert "dagmanager_active_version_weight" in data


def test_diff_duration_and_error_metrics():
    metrics.reset_metrics()
    service = DiffService(FakeRepo(), FakeQueue(), FakeStream())
    service.diff(DiffRequest(strategy_id="s", dag_json=_make_dag()))
    assert get_metric_value(metrics.diff_duration_ms_p95) > 0

    service_err = DiffService(FakeRepo(), FailingQueue(), FakeStream())
    with pytest.raises(RuntimeError):
        service_err.diff(DiffRequest(strategy_id="s", dag_json=_make_dag()))
    assert get_metric_value(metrics.queue_create_error_total) == 1


def test_gc_sets_orphan_gauge():
    metrics.reset_metrics()
    now = datetime.now(UTC)
    store = [QueueInfo("q", "raw", now - timedelta(days=10))]

    class Store:
        def list_orphan_queues(self):
            return list(store)

        def drop_queue(self, name: str) -> None:
            pass

    gc = GarbageCollector(Store(), DummyMetrics())
    gc.collect(now)
    assert get_metric_value(metrics.orphan_queue_total) == 1


def test_metrics_server_exposes_http():
    metrics.reset_metrics()
    metrics.diff_duration_ms_p95.set(42)
    # Pick a free port to avoid collisions in shared CI runners
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("localhost", 0))
        port = s.getsockname()[1]
    metrics.start_metrics_server(port)
    while True:
        try:
            resp = httpx.get(f"http://localhost:{port}/metrics")
            break
        except Exception:
            continue
    assert resp.status_code == 200
    assert "diff_duration_ms_p95" in resp.text


def test_cache_view_metrics_increment():
    from qmtl.runtime.sdk import metrics as sdk_metrics
    from qmtl.runtime.sdk.node import NodeCache

    sdk_metrics.reset_metrics()
    cache = NodeCache(period=2)
    cache.append("u1", 60, 1, {"v": 1})

    view = cache.view(track_access=True)
    _ = view["u1"][60].latest()

    assert sdk_metrics.cache_read_total.labels(
        upstream_id="u1", interval="60"
    )._value.get() == 1
    assert (
        get_metric_value(
            sdk_metrics.cache_last_read_timestamp,
            {"upstream_id": "u1", "interval": "60"},
        )
        > 0
    )


def test_dagmanager_nodecache_metric_aggregates():
    metrics.reset_metrics()
    metrics.observe_nodecache_resident_bytes("n1", 10)
    metrics.observe_nodecache_resident_bytes("n2", 20)
    store = get_mapping_store(metrics.nodecache_resident_bytes, dict)
    assert store[("n1", "node")] == 10
    assert store[("all", "total")] == 30


def test_sdk_nodecache_metric_updates():
    from qmtl.runtime.sdk import metrics as sdk_metrics
    from qmtl.runtime.sdk.node import StreamInput, ProcessingNode
    from qmtl.runtime.sdk.runner import Runner

    sdk_metrics.reset_metrics()
    src = StreamInput(interval="60s", period=2)
    node = ProcessingNode(
        input=src, compute_fn=lambda v: None, name="n", interval="60s", period=2
    )
    Runner.feed_queue_data(node, src.node_id, 60, 60, {"v": 1})
    expected = node.cache.resident_bytes
    node_store = get_mapping_store(sdk_metrics.nodecache_resident_bytes, dict)
    assert node_store[(node.node_id, "node")] == expected
    assert node_store[("all", "total")] == expected


def test_metrics_cli_parses_port(monkeypatch):
    metrics.reset_metrics()
    captured = {}

    def fake_start(port):
        captured["port"] = port

    monkeypatch.setattr(metrics, "start_metrics_server", fake_start)
    monkeypatch.setattr(metrics, "_run_forever", lambda: None)
    metrics.main(["--port", "9100"])
    assert captured["port"] == 9100
