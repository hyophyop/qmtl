import pytest

from qmtl.dagmanager.kafka_admin import KafkaAdmin, InMemoryAdminClient, TopicExistsError
from qmtl.dagmanager.diff_service import KafkaQueueManager
from qmtl.dagmanager.topic import TopicConfig


def test_in_memory_admin_create_and_list():
    client = InMemoryAdminClient()
    admin = KafkaAdmin(client)
    manager = KafkaQueueManager(admin, TopicConfig(1, 1, 1000))

    topic = manager.upsert("asset", "N", "abcd", "v1")

    assert topic in client.list_topics()
    assert client.get_size(topic) == 0


def test_in_memory_admin_duplicate_topic():
    client = InMemoryAdminClient()
    client.create_topic("t1", num_partitions=1, replication_factor=1)
    with pytest.raises(TopicExistsError):
        client.create_topic("t1", num_partitions=1, replication_factor=1)

