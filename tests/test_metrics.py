from datetime import datetime, timedelta

import pytest

from qmtl.dagmanager.diff_service import DiffService, DiffRequest, NodeRepository, QueueManager, StreamSender
from qmtl.dagmanager.gc import GarbageCollector, QueueInfo
from qmtl.dagmanager import metrics


class FakeRepo(NodeRepository):
    def get_nodes(self, node_ids):
        return {}

    def insert_sentinel(self, sentinel_id, node_ids):
        pass


class FakeQueue(QueueManager):
    def upsert(self, node_id):
        return "topic"


class FailingQueue(QueueManager):
    def upsert(self, node_id):
        raise RuntimeError("fail")


class FakeStream(StreamSender):
    def send(self, chunk):
        pass


class DummyMetrics:
    def __init__(self, val: float = 0) -> None:
        self.val = val

    def messages_in_per_sec(self) -> float:
        return self.val


def _make_dag():
    return '{"nodes": [{"node_id": "A", "code_hash": "c", "schema_hash": "s"}]}'


def test_metrics_exposed():
    metrics.reset_metrics()
    metrics.diff_duration_ms_p95.set(10)
    metrics.queue_create_error_total.inc()
    metrics.orphan_queue_total.set(2)

    data = metrics.collect_metrics()
    assert "diff_duration_ms_p95" in data
    assert "queue_create_error_total" in data
    assert "orphan_queue_total" in data


def test_diff_duration_and_error_metrics():
    metrics.reset_metrics()
    service = DiffService(FakeRepo(), FakeQueue(), FakeStream())
    service.diff(DiffRequest(strategy_id="s", dag_json=_make_dag()))
    assert metrics.diff_duration_ms_p95._val > 0  # type: ignore[attr-defined]

    service_err = DiffService(FakeRepo(), FailingQueue(), FakeStream())
    with pytest.raises(RuntimeError):
        service_err.diff(DiffRequest(strategy_id="s", dag_json=_make_dag()))
    assert metrics.queue_create_error_total._value == 1  # type: ignore[attr-defined]


def test_gc_sets_orphan_gauge():
    metrics.reset_metrics()
    now = datetime.utcnow()
    store = [QueueInfo("q", "raw", now - timedelta(days=10))]

    class Store:
        def list_orphan_queues(self):
            return list(store)

        def drop_queue(self, name: str) -> None:
            pass

    gc = GarbageCollector(Store(), DummyMetrics())
    gc.collect(now)
    assert metrics.orphan_queue_total._val == 1  # type: ignore[attr-defined]
