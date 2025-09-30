import asyncio
import pytest

import asyncio

from qmtl.services.dagmanager.buffer_scheduler import BufferingScheduler
from qmtl.services.dagmanager.diff_service import DiffService, DiffRequest, NodeRepository, NodeRecord
from qmtl.services.dagmanager.topic import topic_name


class FakeRepo(NodeRepository):
    def __init__(self, done: asyncio.Event | None = None):
        self.records: dict[str, NodeRecord] = {}
        self.buffered: dict[str, dict[str, int]] = {}
        self.cleared: list[str] = []
        self.done = done or asyncio.Event()

    def get_nodes(self, node_ids):
        return {nid: self.records[nid] for nid in node_ids if nid in self.records}

    def insert_sentinel(self, sentinel_id, node_ids, version):
        pass

    def get_queues_by_tag(self, tags, interval, match_mode="any"):
        return []

    def get_node_by_queue(self, queue):
        return None

    def mark_buffering(self, node_id, *, compute_key=None, timestamp_ms=None):
        key = compute_key or "__global__"
        self.buffered.setdefault(node_id, {})[key] = timestamp_ms or 0

    def clear_buffering(self, node_id, *, compute_key=None):
        self.cleared.append(node_id)
        if compute_key:
            ctx = self.buffered.get(node_id)
            if isinstance(ctx, dict):
                ctx.pop(compute_key, None)
                if not ctx:
                    self.buffered.pop(node_id, None)
        else:
            self.buffered.pop(node_id, None)
        self.done.set()

    def get_buffering_nodes(self, older_than_ms, *, compute_key=None):
        result = []
        for node_id, ctx in self.buffered.items():
            if compute_key:
                ts = ctx.get(compute_key)
                if ts is not None and ts < older_than_ms:
                    result.append(node_id)
            elif any(ts is not None and ts < older_than_ms for ts in ctx.values()):
                result.append(node_id)
        return result


class FakeDiff(DiffService):
    def __init__(self):
        self.calls = []
        self.event = asyncio.Event()

    def diff(self, request: DiffRequest):
        self.calls.append(request)
        self.event.set()
        return type("Chunk", (), {"queue_map": {}, "sentinel_id": request.strategy_id})()


@pytest.mark.asyncio
async def test_scheduler_reprocesses_old_nodes():
    done = asyncio.Event()
    repo = FakeRepo(done)
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
    await asyncio.wait_for(diff.event.wait(), timeout=1)
    await sched.stop()
    assert diff.calls and diff.calls[0].strategy_id == "A"
    assert repo.cleared == ["A"]
