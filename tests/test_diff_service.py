import json
import pytest

# Suppress unraisable exceptions from third-party libs (sockets/event loops)
pytestmark = [
    pytest.mark.filterwarnings('ignore::pytest.PytestUnraisableExceptionWarning'),
    pytest.mark.filterwarnings('ignore:unclosed <socket.socket[^>]*>'),
    pytest.mark.filterwarnings('ignore:unclosed event loop'),
]
from qmtl.dagmanager.diff_service import (
    DiffService,
    DiffRequest,
    NodeRepository,
    QueueManager,
    StreamSender,
    NodeRecord,
    Neo4jNodeRepository,
    KafkaQueueManager,
)
from qmtl.dagmanager.monitor import AckStatus
from qmtl.dagmanager.node_repository import MemoryNodeRepository
from qmtl.dagmanager.kafka_admin import KafkaAdmin, partition_key
from qmtl.dagmanager.topic import topic_name
from qmtl.dagmanager import metrics


class FakeRepo(NodeRepository):
    def __init__(self):
        self.fetched = []
        self.sentinels = []
        self.records = {}
        self.buffered: dict[str, int] = {}

    def get_nodes(self, node_ids):
        self.fetched.append(list(node_ids))
        return {nid: self.records[nid] for nid in node_ids if nid in self.records}

    def insert_sentinel(self, sentinel_id, node_ids, version):
        self.sentinels.append((sentinel_id, list(node_ids), version))

    def get_queues_by_tag(self, tags, interval, match_mode="any"):
        return []

    def mark_buffering(self, node_id, *, timestamp_ms=None):
        self.buffered[node_id] = timestamp_ms or 0

    def clear_buffering(self, node_id):
        self.buffered.pop(node_id, None)

    def get_buffering_nodes(self, older_than_ms):
        return [n for n, t in self.buffered.items() if t < older_than_ms]


class FakeQueue(QueueManager):
    def __init__(self):
        self.calls = []

    def upsert(
        self, asset, node_type, code_hash, version, *, dry_run=False, namespace=None
    ):
        self.calls.append((asset, node_type, code_hash, version, dry_run, namespace))
        return topic_name(
            asset, node_type, code_hash, version, dry_run=dry_run, namespace=namespace
        )


class FakeStream(StreamSender):
    def __init__(self):
        self.chunks = []
        self.waits = 0

    def send(self, chunk):
        self.chunks.append(chunk)

    def wait_for_ack(self) -> AckStatus:
        self.waits += 1
        return AckStatus.OK

    def ack(self, status: AckStatus = AckStatus.OK):
        pass


class TimeoutOnceStream(StreamSender):
    """Stream that times out once before acknowledging."""

    def __init__(self):
        self.chunks = []
        self.waits = 0
        self.resumes = 0

    def send(self, chunk):
        self.chunks.append(chunk)

    def wait_for_ack(self) -> AckStatus:
        self.waits += 1
        return AckStatus.TIMEOUT if self.waits == 1 else AckStatus.OK

    def ack(self, status: AckStatus = AckStatus.OK):
        pass

    def resume_from_last_offset(self):
        self.resumes += 1


def _make_dag(nodes):
    return json.dumps({"nodes": nodes})


def test_pre_scan_and_db_fetch_topo_order():
    repo = FakeRepo()
    queue = FakeQueue()
    stream = FakeStream()
    service = DiffService(repo, queue, stream)

    dag = _make_dag([
        {
            "node_id": "B",
            "node_type": "N",
            "code_hash": "c2",
            "schema_hash": "s2",
            "inputs": ["A"],
        },
        {"node_id": "A", "node_type": "N", "code_hash": "c1", "schema_hash": "s1"},
    ])
    req = DiffRequest(strategy_id="s", dag_json=dag)

    service.diff(req)
    assert repo.fetched[0] == ["A", "B"]


def test_pre_scan_and_db_fetch():
    repo = FakeRepo()
    queue = FakeQueue()
    stream = FakeStream()
    service = DiffService(repo, queue, stream)

    dag = _make_dag([
        {"node_id": "A", "node_type": "N", "code_hash": "c1", "schema_hash": "s1"},
        {"node_id": "B", "node_type": "N", "code_hash": "c2", "schema_hash": "s2"},
    ])
    req = DiffRequest(strategy_id="s", dag_json=dag)

    service.diff(req)
    assert repo.fetched[0] == ["A", "B"]


def test_hash_compare_and_queue_upsert():
    repo = FakeRepo()
    # existing node A
    repo.records["A"] = NodeRecord(
        "A",
        "N",
        "c1",
        "s1",
        "id1",
        None,
        None,
        [],
        None,
        False,
        topic_name("asset", "N", "c1", "v1"),
    )
    queue = FakeQueue()
    stream = FakeStream()
    service = DiffService(repo, queue, stream)

    dag = _make_dag([
        {"node_id": "A", "node_type": "N", "code_hash": "c1", "schema_hash": "s1"},
        {"node_id": "B", "node_type": "N", "code_hash": "c2", "schema_hash": "s2"},
    ])
    req = DiffRequest(strategy_id="s", dag_json=dag)

    chunk = service.diff(req)
    expected_a = topic_name("asset", "N", "c1", "v1")
    expected_b = topic_name("asset", "N", "c2", "v1")
    assert chunk.queue_map[partition_key("A", None, None)] == expected_a
    assert chunk.queue_map[partition_key("B", None, None)] == expected_b
    assert queue.calls == [("asset", "N", "c2", "v1", False, None)]


def test_namespace_applied_to_queue_names(monkeypatch):
    repo = FakeRepo()
    repo.records["A"] = NodeRecord(
        "A",
        "N",
        "c1",
        "s1",
        "id1",
        None,
        None,
        [],
        None,
        False,
        topic_name("asset", "N", "c1", "v1"),
    )
    queue = FakeQueue()
    stream = FakeStream()
    service = DiffService(repo, queue, stream)

    dag = json.dumps(
        {
            "nodes": [
                {
                    "node_id": "A",
                    "node_type": "N",
                    "code_hash": "c1",
                    "schema_hash": "s1",
                },
                {
                    "node_id": "B",
                    "node_type": "N",
                    "code_hash": "c2",
                    "schema_hash": "s2",
                },
            ],
            "meta": {
                "topic_namespace": {"world": "World-1", "domain": "Live"},
            },
        }
    )

    monkeypatch.setenv("QMTL_ENABLE_TOPIC_NAMESPACE", "1")

    chunk = service.diff(DiffRequest(strategy_id="s", dag_json=dag))

    existing_topic = chunk.queue_map[partition_key("A", None, None)]
    new_topic = chunk.queue_map[partition_key("B", None, None)]
    assert existing_topic.startswith("world-1.live.")
    assert new_topic.startswith("world-1.live.")
    assert queue.calls[-1][5] == "world-1.live"


def test_schema_change_buffering_flag():
    repo = FakeRepo()
    repo.records["A"] = NodeRecord(
        "A",
        "N",
        "c1",
        "old",
        "id1",
        None,
        None,
        [],
        None,
        False,
        topic_name("asset", "N", "c1", "v1"),
    )
    queue = FakeQueue()
    stream = FakeStream()
    service = DiffService(repo, queue, stream)

    dag = _make_dag([
        {"node_id": "A", "node_type": "N", "code_hash": "c1", "schema_hash": "new", "period": 3},
    ])
    chunk = service.diff(DiffRequest(strategy_id="s", dag_json=dag))

    expected_a = topic_name("asset", "N", "c1", "v1")
    assert chunk.queue_map[partition_key("A", None, None)] == expected_a
    assert queue.calls == []
    assert not chunk.new_nodes
    assert [n.node_id for n in chunk.buffering_nodes] == ["A"]
    assert chunk.buffering_nodes[0].lag == 3


def test_sentinel_insert_and_stream():
    repo = FakeRepo()
    queue = FakeQueue()
    stream = FakeStream()
    service = DiffService(repo, queue, stream)

    dag = _make_dag([
        {"node_id": "A", "node_type": "N", "code_hash": "c1", "schema_hash": "s1"},
    ])
    req = DiffRequest(strategy_id="strategy", dag_json=dag)

    chunk = service.diff(req)

    assert repo.sentinels == [("strategy-sentinel", ["A"], "v1")]
    assert stream.chunks[0] == chunk
    assert chunk.sentinel_id == "strategy-sentinel"


def test_version_extracted_from_sentinel_node():
    repo = FakeRepo()
    queue = FakeQueue()
    stream = FakeStream()
    service = DiffService(repo, queue, stream)

    dag = json.dumps(
        {
            "nodes": [
                {
                    "node_id": "A",
                    "node_type": "N",
                    "code_hash": "c1",
                    "schema_hash": "s1",
                    "tags": ["btc"],
                },
                {
                    "node_id": "sentinel-node",
                    "node_type": "VersionSentinel",
                    "version": "release-2025.09",
                },
            ]
        }
    )

    chunk = service.diff(DiffRequest(strategy_id="sid", dag_json=dag))

    # normalized version should flow into topics, chunk and sentinel storage
    assert queue.calls[-1][3] == "release-2025.09"
    assert chunk.version == "release-2025.09"
    assert repo.sentinels[-1] == (
        "sid-sentinel",
        ["A"],
        "release-2025.09",
    )


def test_stream_resumes_after_timeout():
    repo = FakeRepo()
    queue = FakeQueue()
    stream = TimeoutOnceStream()
    service = DiffService(repo, queue, stream)

    dag = _make_dag([
        {"node_id": "A", "node_type": "N", "code_hash": "c1", "schema_hash": "s1"},
    ])
    service.diff(DiffRequest(strategy_id="s", dag_json=dag))

    assert stream.resumes == 1
    assert stream.waits == 2


def test_diff_with_sdk_nodes():
    """End-to-end check with nodes serialized by the SDK."""
    from qmtl.sdk import StreamInput, ProcessingNode, Strategy

    class _S(Strategy):
        def setup(self):
            src = StreamInput(interval="1s", period=1)
            node = ProcessingNode(input=src, compute_fn=lambda x: x, name="out", interval="1s", period=1)
            self.add_nodes([src, node])

    s = _S()
    s.setup()
    dag_json = json.dumps(s.serialize())

    repo = FakeRepo()
    queue = FakeQueue()
    stream = FakeStream()
    service = DiffService(repo, queue, stream)

    chunk = service.diff(DiffRequest(strategy_id="sid", dag_json=dag_json))
    # ensure no KeyError and queue map populated
    assert chunk.queue_map


class FakeSession:
    def __init__(self, records=None):
        self.records = records or []
        self.run_calls = []

    def run(self, query, **params):
        self.run_calls.append((query, params))
        return self.records

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        pass


class FakeDriver:
    def __init__(self, records=None):
        self.session_obj = FakeSession(records)

    def session(self):
        return self.session_obj


class FakeAdmin:
    def __init__(self, topics=None):
        self.created = []
        self.topics = topics or {}

    def list_topics(self):
        return self.topics

    def create_topic(self, name, *, num_partitions, replication_factor, config=None):
        self.created.append((name, num_partitions, replication_factor, config))


def test_integration_with_backends():
    """DiffService using Neo4jNodeRepository and KafkaQueueManager."""
    records = [
        {
            "node_id": "A",
            "code_hash": "c1",
            "schema_hash": "s1",
            "topic": topic_name("asset", "N", "c1", "v1"),
        }
    ]
    driver = FakeDriver(records)
    admin = FakeAdmin()
    stream = FakeStream()
    repo = Neo4jNodeRepository(driver)
    queue_manager = KafkaQueueManager(KafkaAdmin(admin))
    service = DiffService(repo, queue_manager, stream)

    dag = _make_dag([
        {"node_id": "A", "node_type": "N", "code_hash": "c1", "schema_hash": "s1"},
        {"node_id": "B", "node_type": "N", "code_hash": "c2", "schema_hash": "s2"},
    ])

    chunk = service.diff(DiffRequest(strategy_id="s", dag_json=dag))

    expected_a = topic_name("asset", "N", "c1", "v1")
    expected_b = topic_name("asset", "N", "c2", "v1")
    assert chunk.queue_map == {
        partition_key("A", None, None): expected_a,
        partition_key("B", None, None): expected_b,
    }
    assert any("sid" in p for _, p in driver.session_obj.run_calls)
    assert admin.created and admin.created[0][0] == expected_b
    assert stream.chunks[0] == chunk


def test_integration_with_memory_repo(tmp_path):
    path = tmp_path / "mem.gpickle"
    repo = MemoryNodeRepository(str(path))
    repo.add_node(
        NodeRecord(
            "A",
            "N",
            "c1",
            "s1",
            "id1",
            None,
            None,
            [],
            None,
            False,
            topic_name("asset", "N", "c1", "v1"),
        )
    )
    queue = FakeQueue()
    stream = FakeStream()
    service = DiffService(repo, queue, stream)

    dag = _make_dag([
        {"node_id": "A", "node_type": "N", "code_hash": "c1", "schema_hash": "s1"},
        {"node_id": "B", "node_type": "N", "code_hash": "c2", "schema_hash": "s2"},
    ])

    chunk = service.diff(DiffRequest(strategy_id="s", dag_json=dag))

    expected_a = topic_name("asset", "N", "c1", "v1")
    expected_b = topic_name("asset", "N", "c2", "v1")
    assert chunk.queue_map == {
        partition_key("A", None, None): expected_a,
        partition_key("B", None, None): expected_b,
    }
    # ensure persistence
    repo2 = MemoryNodeRepository(str(path))
    assert "A" in repo2.get_nodes(["A"])


def test_sentinel_gap_metric_increment():
    metrics.reset_metrics()
    repo = FakeRepo()
    repo.records["A"] = NodeRecord(
        "A",
        "N",
        "c1",
        "s1",
        "id1",
        None,
        None,
        [],
        None,
        topic_name("asset", "N", "c1", "v1"),
    )
    queue = FakeQueue()
    stream = FakeStream()
    service = DiffService(repo, queue, stream)

    dag = _make_dag([
        {"node_id": "A", "node_type": "N", "code_hash": "c1", "schema_hash": "s1"},
    ])

    service.diff(DiffRequest(strategy_id="s", dag_json=dag))
    assert metrics.sentinel_gap_count._value.get() == 1  # type: ignore[attr-defined]


def test_pre_scan_uses_custom_json_loader(monkeypatch):
    calls = []

    def fake_loads(data):
        calls.append(data)
        return {"nodes": []}

    import qmtl.dagmanager.diff_service as mod

    monkeypatch.setattr(mod, "_json_loads", fake_loads)

    repo = FakeRepo()
    queue = FakeQueue()
    stream = FakeStream()
    service = DiffService(repo, queue, stream)

    service.diff(DiffRequest(strategy_id="s", dag_json="{}"))
    assert calls == ["{}"]


@pytest.mark.filterwarnings("ignore:unclosed <socket.socket[^>]*>")
@pytest.mark.filterwarnings("ignore:unclosed event loop")
def test_stream_chunking_and_ack():
    repo = FakeRepo()
    queue = FakeQueue()
    stream = FakeStream()
    service = DiffService(repo, queue, stream)

    nodes = [
        {"node_id": str(i), "node_type": "N", "code_hash": "c", "schema_hash": "s"}
        for i in range(250)
    ]
    dag = _make_dag(nodes)
    service.diff(DiffRequest(strategy_id="s", dag_json=dag))

    assert len(stream.chunks) == 3
    assert stream.waits == 3
