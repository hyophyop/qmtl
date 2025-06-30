from datetime import datetime, timedelta, UTC

import pytest

from qmtl.dagmanager.diff_service import (
    DiffService,
    DiffRequest,
    NodeRepository,
    QueueManager,
    StreamSender,
)
from qmtl.dagmanager.topic import topic_name
from qmtl.dagmanager.gc import GarbageCollector, QueueInfo
import httpx
import time
from qmtl.dagmanager import metrics


class FakeRepo(NodeRepository):
    def get_nodes(self, node_ids):
        return {}

    def insert_sentinel(self, sentinel_id, node_ids):
        pass

    def get_queues_by_tag(self, tags, interval, match_mode="any"):
        return []

    def mark_buffering(self, node_id, *, timestamp_ms=None):
        pass

    def clear_buffering(self, node_id):
        pass

    def get_buffering_nodes(self, older_than_ms):
        return []


class FakeQueue(QueueManager):
    def upsert(self, asset, node_type, code_hash, version, *, dryrun=False):
        return topic_name(asset, node_type, code_hash, version, dryrun=dryrun)


class FailingQueue(QueueManager):
    def upsert(self, asset, node_type, code_hash, version, *, dryrun=False):
        raise RuntimeError("fail")


class FakeStream(StreamSender):
    def send(self, chunk):
        pass

    def wait_for_ack(self):
        pass

    def ack(self):
        pass


class DummyMetrics:
    def __init__(self, val: float = 0) -> None:
        self.val = val

    def messages_in_per_sec(self) -> float:
        return self.val


def _make_dag():
    return (
        '{"nodes": ['
        '{"node_id": "A", "node_type": "N", "code_hash": "c", "schema_hash": "s"}'
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
    assert "active_version_weight" in data


def test_diff_duration_and_error_metrics():
    metrics.reset_metrics()
    service = DiffService(FakeRepo(), FakeQueue(), FakeStream())
    service.diff(DiffRequest(strategy_id="s", dag_json=_make_dag()))
    assert metrics.diff_duration_ms_p95._value.get() > 0  # type: ignore[attr-defined]

    service_err = DiffService(FakeRepo(), FailingQueue(), FakeStream())
    with pytest.raises(RuntimeError):
        service_err.diff(DiffRequest(strategy_id="s", dag_json=_make_dag()))
    assert metrics.queue_create_error_total._value.get() == 1  # type: ignore[attr-defined]


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
    assert metrics.orphan_queue_total._value.get() == 1  # type: ignore[attr-defined]


def test_metrics_server_exposes_http():
    metrics.reset_metrics()
    metrics.diff_duration_ms_p95.set(42)
    port = 9101
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
    from qmtl.sdk import metrics as sdk_metrics
    from qmtl.sdk.node import NodeCache

    sdk_metrics.reset_metrics()
    cache = NodeCache(period=2)
    cache.append("u1", 60, 1, {"v": 1})

    view = cache.view(track_access=True)
    _ = view["u1"][60].latest()

    assert sdk_metrics.cache_read_total.labels(
        upstream_id="u1", interval="60"
    )._value.get() == 1
    assert (
        sdk_metrics.cache_last_read_timestamp.labels(
            upstream_id="u1", interval="60"
        )._value.get()
        > 0
    )
