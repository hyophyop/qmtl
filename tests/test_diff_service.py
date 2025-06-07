import json
from qmtl.dagmanager.diff_service import (
    DiffService,
    DiffRequest,
    NodeRepository,
    QueueManager,
    StreamSender,
    NodeRecord,
)


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


class FakeQueue(QueueManager):
    def __init__(self):
        self.calls = []

    def upsert(self, node_id):
        self.calls.append(node_id)
        return f"topic_{node_id}"


class FakeStream(StreamSender):
    def __init__(self):
        self.chunks = []

    def send(self, chunk):
        self.chunks.append(chunk)


def _make_dag(nodes):
    return json.dumps({"nodes": nodes})


def test_pre_scan_and_db_fetch():
    repo = FakeRepo()
    queue = FakeQueue()
    stream = FakeStream()
    service = DiffService(repo, queue, stream)

    dag = _make_dag([
        {"node_id": "A", "code_hash": "c1", "schema_hash": "s1"},
        {"node_id": "B", "code_hash": "c2", "schema_hash": "s2"},
    ])
    req = DiffRequest(strategy_id="s", dag_json=dag)

    service.diff(req)
    assert repo.fetched[0] == ["A", "B"]


def test_hash_compare_and_queue_upsert():
    repo = FakeRepo()
    # existing node A
    repo.records["A"] = NodeRecord("A", "c1", "s1", "topic_A")
    queue = FakeQueue()
    stream = FakeStream()
    service = DiffService(repo, queue, stream)

    dag = _make_dag([
        {"node_id": "A", "code_hash": "c1", "schema_hash": "s1"},
        {"node_id": "B", "code_hash": "c2", "schema_hash": "s2"},
    ])
    req = DiffRequest(strategy_id="s", dag_json=dag)

    chunk = service.diff(req)
    assert chunk.queue_map["A"] == "topic_A"
    assert chunk.queue_map["B"] == "topic_B"
    assert queue.calls == ["B"]


def test_sentinel_insert_and_stream():
    repo = FakeRepo()
    queue = FakeQueue()
    stream = FakeStream()
    service = DiffService(repo, queue, stream)

    dag = _make_dag([
        {"node_id": "A", "code_hash": "c1", "schema_hash": "s1"},
    ])
    req = DiffRequest(strategy_id="strategy", dag_json=dag)

    chunk = service.diff(req)

    assert repo.sentinels == [("strategy-sentinel", ["A"])]
    assert stream.chunks[0] == chunk
    assert chunk.sentinel_id == "strategy-sentinel"
