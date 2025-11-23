import asyncio

import pytest

from qmtl.foundation.common.metrics_factory import get_mapping_store
from qmtl.services.dagmanager.kafka_admin import KafkaAdmin, InMemoryAdminClient
from qmtl.services.dagmanager.lag_monitor import LagMonitor, LagMonitorLoop, QueueLagInfo
from qmtl.services.dagmanager import metrics


class DummyStore:
    def __init__(self, infos):
        self._infos = infos

    def list_queues(self):
        return self._infos


def test_kafka_admin_topic_lag():
    client = InMemoryAdminClient()
    client.create_topic("t1", num_partitions=1, replication_factor=1)
    client.set_offsets("t1", high=100, low=0)
    admin = KafkaAdmin(client)

    lags = admin.topic_lag({"t1": 90})
    assert lags["t1"] == 10


def test_lag_monitor_records_metrics():
    client = InMemoryAdminClient()
    client.create_topic("q1", num_partitions=1, replication_factor=1)
    client.set_offsets("q1", high=15, low=0)
    admin = KafkaAdmin(client)

    store = DummyStore([QueueLagInfo(topic="q1", committed_offset=5, lag_alert_threshold=10)])

    metrics.reset_metrics()
    monitor = LagMonitor(admin, store)
    lags = monitor.record_lag()

    assert lags["q1"] == 10
    lag_store = get_mapping_store(metrics.queue_lag_seconds, dict)
    threshold_store = get_mapping_store(metrics.queue_lag_threshold_seconds, dict)
    assert lag_store["q1"] == 10
    assert threshold_store["q1"] == 10


def test_lag_monitor_defaults_missing_lag_to_zero():
    client = InMemoryAdminClient()
    client.create_topic("q1", num_partitions=1, replication_factor=1)
    admin = KafkaAdmin(client)

    store = DummyStore(
        [QueueLagInfo(topic="q1", committed_offset=7, lag_alert_threshold=3)]
    )

    metrics.reset_metrics()
    monitor = LagMonitor(admin, store)

    lags = monitor.record_lag()

    assert lags == {"q1": 0}
    lag_store = get_mapping_store(metrics.queue_lag_seconds, dict)
    threshold_store = get_mapping_store(metrics.queue_lag_threshold_seconds, dict)
    assert lag_store["q1"] == 0
    assert threshold_store["q1"] == 3


def test_lag_monitor_updates_existing_metrics():
    client = InMemoryAdminClient()
    client.create_topic("q1", num_partitions=1, replication_factor=1)
    client.set_offsets("q1", high=120, low=0)
    admin = KafkaAdmin(client)

    store = DummyStore(
        [QueueLagInfo(topic="q1", committed_offset=60, lag_alert_threshold=30)]
    )

    metrics.reset_metrics()
    monitor = LagMonitor(admin, store)

    first_lags = monitor.record_lag()
    assert first_lags["q1"] == 60

    # Simulate catching up to the head offset and ensure the gauges clear.
    store._infos = [QueueLagInfo(topic="q1", committed_offset=120, lag_alert_threshold=30)]
    client.set_offsets("q1", high=120, low=0)

    updated_lags = monitor.record_lag()

    lag_store = get_mapping_store(metrics.queue_lag_seconds, dict)
    threshold_store = get_mapping_store(metrics.queue_lag_threshold_seconds, dict)
    assert updated_lags["q1"] == 0
    assert lag_store["q1"] == 0
    assert threshold_store["q1"] == 30


@pytest.mark.asyncio
async def test_lag_monitor_loop_runs_and_stops():
    calls = 0
    ready = asyncio.Event()

    class RecordingMonitor(LagMonitor):
        def __init__(self) -> None:
            super().__init__(admin=None, store=None)  # type: ignore[arg-type]

        def record_lag(self):  # type: ignore[override]
            nonlocal calls
            calls += 1
            if calls >= 2:
                ready.set()

    loop = LagMonitorLoop(RecordingMonitor(), interval=0.01)

    await loop.start()
    await asyncio.wait_for(ready.wait(), timeout=0.2)
    await loop.stop()

    assert calls >= 2
    assert loop._task is None
