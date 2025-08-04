import json
import hashlib

from qmtl.dagmanager import compute_node_id
from qmtl.dagmanager.diff_service import (
    DiffService,
    DiffRequest,
    NodeRepository,
    NodeRecord,
    QueueManager,
    StreamSender,
)


class Repo(NodeRepository):
    def __init__(self) -> None:
        self.records: dict[str, NodeRecord] = {}

    def add_node(self, record: NodeRecord) -> None:
        self.records[record.node_id] = record

    def get_nodes(self, node_ids, *, breaker=None):
        return {nid: self.records[nid] for nid in node_ids if nid in self.records}

    def insert_sentinel(self, sentinel_id, node_ids, *, breaker=None):
        pass

    def get_queues_by_tag(self, tags, interval, match_mode="any", *, breaker=None):
        return []

    def get_node_by_queue(self, queue, *, breaker=None):
        return None

    def mark_buffering(self, node_id, *, timestamp_ms=None, breaker=None):
        pass

    def clear_buffering(self, node_id, *, breaker=None):
        pass

    def get_buffering_nodes(self, older_than_ms, *, breaker=None):
        return []


class Queue(QueueManager):
    def __init__(self) -> None:
        self.calls = []

    def upsert(self, asset, node_type, code_hash, version, *, dryrun=False):
        self.calls.append((asset, node_type, code_hash, version, dryrun))
        return f"{asset}-{node_type}-{code_hash}-{version}"


class Stream(StreamSender):
    def __init__(self) -> None:
        self.chunks = []

    def send(self, chunk):
        self.chunks.append(chunk)

    def ack(self) -> None:  # pragma: no cover - interface requirement
        pass


def _dag_json(node_id: str) -> str:
    dag = {
        "nodes": [
            {
                "node_id": node_id,
                "node_type": "N",
                "code_hash": "c1",
                "schema_hash": "s1",
            }
        ]
    }
    return json.dumps(dag)


def test_queue_reuse_across_strategies():
    repo = Repo()
    queue = Queue()
    stream = Stream()
    service = DiffService(repo, queue, stream)

    node_id = "shared-node"
    dag = _dag_json(node_id)

    first = service.diff(DiffRequest(strategy_id="s1", dag_json=dag))
    repo.add_node(
        NodeRecord(
            node_id,
            "N",
            "c1",
            "s1",
            None,
            None,
            [],
            first.queue_map[node_id],
        )
    )

    second = service.diff(DiffRequest(strategy_id="s2", dag_json=dag))

    assert len(queue.calls) == 1
    assert second.queue_map[node_id] == first.queue_map[node_id]


def test_compute_node_id_collision_fallback():
    data = ("A", "B", "C", "D")
    first = compute_node_id(*data)
    second = compute_node_id(*data, existing_ids={first})
    assert first != second
    assert second == hashlib.sha3_256(b"A:B:C:D").hexdigest()
