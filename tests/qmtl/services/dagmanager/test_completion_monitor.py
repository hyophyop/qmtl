import pytest

from qmtl.services.dagmanager.completion import QueueCompletionMonitor
from qmtl.services.dagmanager.diff_service import NodeRecord, NodeRepository
from qmtl.services.dagmanager.kafka_admin import KafkaAdmin
from qmtl.services.dagmanager.controlbus_producer import ControlBusProducer


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


class RecordingBus(ControlBusProducer):
    def __init__(self) -> None:
        self.published: list[tuple] = []

    async def publish_queue_update(
        self, tags, interval, queues, match_mode: str = "any", *, version: int = 1
    ) -> None:  # type: ignore[override]
        self.published.append((list(tags), interval, list(queues), match_mode, version))


class StaticRepo(NodeRepository):
    def __init__(self, record: NodeRecord | None) -> None:
        self.record = record

    def get_nodes(self, node_ids):
        return {}

    def insert_sentinel(self, sentinel_id, node_ids, version):
        pass

    def get_queues_by_tag(self, tags, interval, match_mode="any"):
        return []

    def get_node_by_queue(self, queue):
        return self.record


class FixedAdmin(KafkaAdmin):
    def __init__(self, sizes):
        super().__init__(client=None)  # type: ignore[arg-type]
        self._sizes = sizes
        self._calls = 0

    def get_topic_sizes(self):  # type: ignore[override]
        size = self._sizes[self._calls] if self._calls < len(self._sizes) else {}
        self._calls += 1
        return size


@pytest.mark.asyncio
async def test_completion_resets_stall_counter_on_growth():
    repo = DummyRepo()
    bus = RecordingBus()
    admin = FixedAdmin([{"q1": 1}, {"q1": 2}, {"q1": 2}])
    monitor = QueueCompletionMonitor(repo, admin, bus=bus, threshold=1)

    await monitor.check_once()  # baseline
    await monitor.check_once()  # growth resets stall counter
    await monitor.check_once()  # now stalled for one interval

    assert bus.published, "Completion event should fire after growth then stall"
    assert bus.published[0][1] == "60s"


@pytest.mark.asyncio
async def test_completion_emits_only_once_per_topic():
    repo = DummyRepo()
    bus = RecordingBus()
    admin = FixedAdmin([{"q1": 5}, {"q1": 5}, {"q1": 5}])
    monitor = QueueCompletionMonitor(repo, admin, bus=bus, threshold=1)

    await monitor.check_once()
    await monitor.check_once()
    await monitor.check_once()

    assert len(bus.published) == 1
    assert monitor._completed == {"q1"}


@pytest.mark.asyncio
async def test_completion_requires_metadata():
    record = NodeRecord(
        node_id="n2",
        node_type="N",
        code_hash="c",
        schema_hash="s",
        schema_id="id1",
        interval=None,
        period=None,
        tags=[],
        bucket=None,
        is_global=False,
        topic="q2",
    )
    repo = StaticRepo(record)
    bus = RecordingBus()
    admin = FixedAdmin([{"q2": 1}, {"q2": 1}, {"q2": 1}])
    monitor = QueueCompletionMonitor(repo, admin, bus=bus, threshold=2)

    await monitor.check_once()
    await monitor.check_once()
    await monitor.check_once()

    assert bus.published == []
    assert monitor._completed == set()
