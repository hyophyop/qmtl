import pytest

from qmtl.foundation.common.metrics_factory import get_mapping_store
from qmtl.services.dagmanager.kafka_admin import KafkaAdmin, InMemoryAdminClient
from qmtl.services.dagmanager.lag_monitor import LagMonitor, QueueLagInfo
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
