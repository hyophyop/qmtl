import httpx
import pytest

from qmtl.dagmanager.completion import QueueCompletionMonitor
from qmtl.dagmanager.diff_service import NodeRecord, NodeRepository
from qmtl.dagmanager.kafka_admin import KafkaAdmin


class DummyRepo(NodeRepository):
    def __init__(self) -> None:
        self.rec = NodeRecord(
            node_id="n1",
            node_type="N",
            code_hash="c",
            schema_hash="s",
            interval="60s",
            period=1,
            tags=["t1"],
            topic="q1",
        )

    def get_nodes(self, node_ids):
        return {}

    def insert_sentinel(self, sentinel_id, node_ids):
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


@pytest.mark.asyncio
async def test_completion_emits_event(monkeypatch):
    repo = DummyRepo()
    admin = make_admin([{"q1": 10}, {"q1": 10}])
    events = []

    async def fake_post(url, payload, **_):
        events.append(payload)
        return httpx.Response(202)

    monkeypatch.setattr(
        "qmtl.dagmanager.completion.post",
        fake_post,
    )

    monitor = QueueCompletionMonitor(repo, admin, "http://gw/cb", threshold=1)
    await monitor.check_once()
    await monitor.check_once()

    assert events
    evt = events[0]
    assert evt["type"] == "queue_update"
    assert evt["data"]["queues"] == []
    assert evt["data"]["tags"] == ["t1"]
    assert evt["data"]["match_mode"] == "any"
