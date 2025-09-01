import asyncio
import pytest

from qmtl.dagmanager.buffer_scheduler import BufferingScheduler
from qmtl.dagmanager.diff_service import DiffService, DiffRequest, NodeRepository, NodeRecord
from qmtl.dagmanager.topic import topic_name


class FakeRepo(NodeRepository):
    def __init__(self):
        self.records: dict[str, NodeRecord] = {}
        self.buffered: dict[str, int] = {}
        self.cleared: list[str] = []

    def get_nodes(self, node_ids):
        return {nid: self.records[nid] for nid in node_ids if nid in self.records}

    def insert_sentinel(self, sentinel_id, node_ids):
        pass

    def get_queues_by_tag(self, tags, interval, match_mode="any"):
        return []

    def get_node_by_queue(self, queue):
        return None

    def mark_buffering(self, node_id, *, timestamp_ms=None):
        self.buffered[node_id] = timestamp_ms or 0

    def clear_buffering(self, node_id):
        self.cleared.append(node_id)
        self.buffered.pop(node_id, None)

    def get_buffering_nodes(self, older_than_ms):
        return [n for n, t in self.buffered.items() if t < older_than_ms]


class FakeDiff(DiffService):
    def __init__(self):
        self.calls = []

    def diff(self, request: DiffRequest):
        self.calls.append(request)
        return type("Chunk", (), {"queue_map": {}, "sentinel_id": request.strategy_id})()


@pytest.mark.asyncio
async def test_scheduler_reprocesses_old_nodes():
    repo = FakeRepo()
    repo.records["A"] = NodeRecord(
        "A",
        "N",
        "c",
        "s",
        "id1",
        None,
        None,
        [],
        None,
        False,
        topic_name("asset", "N", "c", "v1"),
    )
    repo.mark_buffering("A", timestamp_ms=0)
    diff = FakeDiff()
    sched = BufferingScheduler(repo, diff, interval=0.01, delay_days=7)
    await sched.start()
    await asyncio.sleep(0.03)
    await sched.stop()
    assert diff.calls and diff.calls[0].strategy_id == "A"
    assert repo.cleared == ["A"]
