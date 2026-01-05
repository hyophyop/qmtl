from __future__ import annotations

from datetime import datetime

from qmtl.services.dagmanager.kafka_admin import InMemoryAdminClient, KafkaAdmin
from qmtl.services.dagmanager.queue_store import KafkaQueueStore
from qmtl.services.dagmanager.metrics_provider import KafkaMetricsProvider
from qmtl.services.dagmanager.repository import NodeRepository
from qmtl.services.dagmanager.models import NodeRecord


class RepoStub(NodeRepository):
    def __init__(self, mapping: dict[str, NodeRecord | None]) -> None:
        self._mapping = mapping

    def get_nodes(self, node_ids, *, breaker=None):  # pragma: no cover - unused
        return {}

    def insert_sentinel(self, sentinel_id, node_ids, version, *, breaker=None):  # pragma: no cover - unused
        raise NotImplementedError

    def get_queues_by_tag(self, tags, interval, match_mode="any", *, breaker=None):  # pragma: no cover - unused
        return []

    def get_node_by_queue(self, queue: str, *, breaker=None):
        return self._mapping.get(queue)

    def mark_buffering(self, node_id, *, compute_key=None, timestamp_ms=None, breaker=None):  # pragma: no cover - unused
        raise NotImplementedError

    def clear_buffering(self, node_id, *, compute_key=None, breaker=None):  # pragma: no cover - unused
        raise NotImplementedError

    def get_buffering_nodes(self, older_than_ms, *, compute_key=None, breaker=None):  # pragma: no cover - unused
        return []


def test_kafka_queue_store_lists_orphans_only():
    admin_client = InMemoryAdminClient()
    admin_client.create_topic(
        "referenced",
        num_partitions=1,
        replication_factor=1,
        config={"qmtl.tag": "raw", "qmtl.interval": "60", "qmtl.created_at": "1700000000"},
    )
    admin_client.create_topic(
        "orphan",
        num_partitions=1,
        replication_factor=1,
        config={"retention.ms": str(7 * 24 * 60 * 60 * 1000)},
    )
    repo = RepoStub({
        "referenced": NodeRecord(
            node_id="n",
            node_type="",
            code_hash="",
            schema_hash="",
            schema_compat_id="",
            interval=60,
            period=None,
            tags=[],
            topic="referenced",
        )
    })
    store = KafkaQueueStore(KafkaAdmin(admin_client), repo)

    orphans = list(store.list_orphan_queues())

    assert [q.name for q in orphans] == ["orphan"]
    assert orphans[0].tag == "raw"
    assert isinstance(orphans[0].created_at, datetime)


def test_kafka_queue_store_drop_deletes_topic():
    admin_client = InMemoryAdminClient()
    admin_client.create_topic(
        "dropme",
        num_partitions=1,
        replication_factor=1,
    )
    store = KafkaQueueStore(KafkaAdmin(admin_client))

    store.drop_queue("dropme")

    assert "dropme" not in admin_client.list_topics()


def test_kafka_metrics_provider_parses_metric():
    payload = """
# HELP kafka_server_BrokerTopicMetrics_MessagesInPerSec
kafka_server_BrokerTopicMetrics_MessagesInPerSec 83.25
"""

    provider = KafkaMetricsProvider("http://example", fetcher=lambda _: payload)

    assert provider.messages_in_per_sec() == 83.25
