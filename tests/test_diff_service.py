import json
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
from qmtl.dagmanager.kafka_admin import KafkaAdmin
from qmtl.dagmanager.topic import topic_name
from qmtl.dagmanager import metrics


class FakeRepo(NodeRepository):
    def __init__(self):
        self.fetched = []
        self.sentinels = []
        self.records = {}

    def get_nodes(self, node_ids):
        self.fetched.append(list(node_ids))
        return {nid: self.records[nid] for nid in node_ids if nid in self.records}

    def insert_sentinel(self, sentinel_id, node_ids):
        self.sentinels.append((sentinel_id, list(node_ids)))

    def get_queues_by_tag(self, tags, interval):
        return []


class FakeQueue(QueueManager):
    def __init__(self):
        self.calls = []

    def upsert(self, asset, node_type, code_hash, version, *, dryrun=False):
        self.calls.append((asset, node_type, code_hash, version, dryrun))
        return topic_name(asset, node_type, code_hash, version, dryrun=dryrun)


class FakeStream(StreamSender):
    def __init__(self):
        self.chunks = []

    def send(self, chunk):
        self.chunks.append(chunk)


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
        None,
        [],
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
    assert chunk.queue_map["A"] == expected_a
    assert chunk.queue_map["B"] == expected_b
    assert queue.calls == [("asset", "N", "c2", "v1", False)]


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

    assert repo.sentinels == [("strategy-sentinel", ["A"])]
    assert stream.chunks[0] == chunk
    assert chunk.sentinel_id == "strategy-sentinel"


def test_diff_with_sdk_nodes():
    """End-to-end check with nodes serialized by the SDK."""
    from qmtl.sdk import StreamInput, Node, Strategy

    class _S(Strategy):
        def setup(self):
            src = StreamInput(interval=1, period=1)
            node = Node(input=src, compute_fn=lambda x: x, name="out", interval=1, period=1)
            self.add_nodes([src, node])

        def define_execution(self):
            self.set_target("out")

    s = _S()
    s.setup()
    s.define_execution()
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
    assert chunk.queue_map == {"A": expected_a, "B": expected_b}
    assert any("sid" in p for _, p in driver.session_obj.run_calls)
    assert admin.created and admin.created[0][0] == expected_b
    assert stream.chunks[0] == chunk


def test_sentinel_gap_metric_increment():
    metrics.reset_metrics()
    repo = FakeRepo()
    repo.records["A"] = NodeRecord(
        "A",
        "N",
        "c1",
        "s1",
        None,
        [],
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
