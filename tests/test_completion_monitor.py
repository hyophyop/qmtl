import pytest

from qmtl.dagmanager.completion import QueueCompletionMonitor
from qmtl.dagmanager.diff_service import NodeRecord, NodeRepository
from qmtl.dagmanager.kafka_admin import KafkaAdmin
from qmtl.dagmanager.controlbus_producer import ControlBusProducer


class DummyRepo(NodeRepository):
    def __init__(self) -> None:
        self.rec = NodeRecord(
            node_id="n1",
            node_type="N",
            code_hash="c",
            schema_hash="s",
            schema_id="id1",
            interval="60s",
            period=1,
            tags=["t1"],
            bucket=None,
            is_global=False,
            topic="q1",
        )

    def get_nodes(self, node_ids):
        return {}

    def insert_sentinel(self, sentinel_id, node_ids, version):
        pass

    def get_queues_by_tag(self, tags, interval, match_mode="any"):
        return []

    def get_node_by_queue(self, queue):
        if queue == "q1":
            return self.rec
        return None


class DummyAdminClient:
    def __init__(self, sizes):
        self.sizes = sizes
        self.calls = 0

    def list_topics(self):
        data = {}
        if self.calls < len(self.sizes):
            for k, v in self.sizes[self.calls].items():
                data[k] = {"size": v}
        self.calls += 1
        return data

    def create_topic(self, *a, **k):
        pass


def make_admin(sizes) -> KafkaAdmin:
    client = DummyAdminClient(sizes)
    return KafkaAdmin(client)


class DummyBus(ControlBusProducer):
    def __init__(self) -> None:  # pragma: no cover - simple capture
        self.published: list[tuple] = []

    async def publish_queue_update(self, tags, interval, queues, match_mode: str = "any", *, version: int = 1) -> None:  # type: ignore[override]
        self.published.append((list(tags), interval, list(queues), match_mode, version))


@pytest.mark.asyncio
async def test_completion_emits_event():
    repo = DummyRepo()
    admin = make_admin([{"q1": 10}, {"q1": 10}])
    bus = DummyBus()
    monitor = QueueCompletionMonitor(repo, admin, bus=bus, threshold=1)
    await monitor.check_once()
    await monitor.check_once()

    assert bus.published
    tags, interval, queues, mode, version = bus.published[0]
    assert queues == []
    assert tags == ["t1"]
    assert mode == "any"
    assert version == 1
