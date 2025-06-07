import asyncio
from datetime import datetime, timedelta

import grpc
import pytest

from qmtl.dagmanager.diff_service import (
    DiffService,
    DiffRequest,
    NodeRepository,
    QueueManager,
    StreamSender,
)
from qmtl.dagmanager.grpc_server import serve
from qmtl.dagmanager.gc import GarbageCollector, QueueInfo
from qmtl.proto import dagmanager_pb2, dagmanager_pb2_grpc


class FakeRepo(NodeRepository):
    def get_nodes(self, node_ids):
        return {}

    def insert_sentinel(self, sentinel_id, node_ids):
        pass


class FakeQueue(QueueManager):
    def upsert(self, node_id):
        return "topic"


class FakeStream(StreamSender):
    def send(self, chunk):
        pass


@pytest.mark.asyncio
async def test_grpc_diff():
    service = DiffService(FakeRepo(), FakeQueue(), FakeStream())
    server, port = serve(service, host="127.0.0.1", port=0)
    await server.start()
    async with grpc.aio.insecure_channel(f"127.0.0.1:{port}") as channel:
        stub = dagmanager_pb2_grpc.DiffServiceStub(channel)
        request = dagmanager_pb2.DiffRequest(strategy_id="s", dag_json="{}")
        responses = [r async for r in stub.Diff(request)]
    await server.stop(None)
    assert responses[0].sentinel_id == "s-sentinel"


class DummyStore:
    def __init__(self, queues):
        self.queues = queues
        self.dropped = []

    def list_orphan_queues(self):
        return list(self.queues)

    def drop_queue(self, name: str) -> None:
        self.dropped.append(name)


class DummyMetrics:
    def __init__(self, val: float = 0) -> None:
        self.val = val

    def messages_in_per_sec(self) -> float:
        return self.val


class DummyArchive:
    def __init__(self):
        self.archived = []

    def archive(self, queue: str) -> None:
        self.archived.append(queue)


@pytest.mark.asyncio
async def test_grpc_cleanup_triggers_gc():
    now = datetime.utcnow()
    store = DummyStore([QueueInfo("q", "raw", now - timedelta(days=10))])
    gc = GarbageCollector(store, DummyMetrics(), batch_size=1)

    service = DiffService(FakeRepo(), FakeQueue(), FakeStream())
    server, port = serve(service, host="127.0.0.1", port=0, gc=gc)
    await server.start()
    async with grpc.aio.insecure_channel(f"127.0.0.1:{port}") as channel:
        stub = dagmanager_pb2_grpc.AdminServiceStub(channel)
        await stub.Cleanup(dagmanager_pb2.CleanupRequest(strategy_id="s"))
    await server.stop(None)
    assert store.dropped == ["q"]


@pytest.mark.asyncio
async def test_grpc_cleanup_archives():
    now = datetime.utcnow()
    store = DummyStore([QueueInfo("s", "sentinel", now - timedelta(days=400))])
    archive = DummyArchive()
    gc = GarbageCollector(store, DummyMetrics(), archive=archive, batch_size=1)

    service = DiffService(FakeRepo(), FakeQueue(), FakeStream())
    server, port = serve(service, host="127.0.0.1", port=0, gc=gc)
    await server.start()
    async with grpc.aio.insecure_channel(f"127.0.0.1:{port}") as channel:
        stub = dagmanager_pb2_grpc.AdminServiceStub(channel)
        await stub.Cleanup(dagmanager_pb2.CleanupRequest(strategy_id="s"))
    await server.stop(None)

    assert store.dropped == ["s"]
    assert archive.archived == ["s"]
