import asyncio
from datetime import datetime, timedelta

import grpc
import pytest
import httpx

from qmtl.dagmanager.diff_service import StreamSender
from qmtl.dagmanager.grpc_server import serve
from qmtl.dagmanager.gc import GarbageCollector, QueueInfo
from qmtl.proto import dagmanager_pb2, dagmanager_pb2_grpc



class FakeSession:
    def __init__(self, result=None):
        self.result = result or []
        self.run_calls = []

    def run(self, query, **params):
        self.run_calls.append((query, params))
        return self.result

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        pass


class FakeDriver:
    def __init__(self):
        self.session_obj = FakeSession()

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


class FakeStream(StreamSender):
    def send(self, chunk):
        pass


@pytest.mark.asyncio
async def test_grpc_diff():
    driver = FakeDriver()
    admin = FakeAdmin()
    stream = FakeStream()
    server, port = serve(driver, admin, stream, host="127.0.0.1", port=0)
    await server.start()
    async with grpc.aio.insecure_channel(f"127.0.0.1:{port}") as channel:
        stub = dagmanager_pb2_grpc.DiffServiceStub(channel)
        request = dagmanager_pb2.DiffRequest(strategy_id="s", dag_json="{}")
        responses = [r async for r in stub.Diff(request)]
    await server.stop(None)
    assert responses[0].sentinel_id == "s-sentinel"


@pytest.mark.asyncio
async def test_grpc_diff_callback_sends_cloudevent(monkeypatch):
    driver = FakeDriver()
    admin = FakeAdmin()
    stream = FakeStream()
    captured: dict = {}

    async def mock_post(url, json, **_):
        captured.update(json)
        return httpx.Response(202)

    monkeypatch.setattr(
        "qmtl.dagmanager.grpc_server.post_with_backoff",
        mock_post,
    )

    server, port = serve(
        driver,
        admin,
        stream,
        host="127.0.0.1",
        port=0,
        callback_url="http://gw/cb",
    )
    await server.start()
    async with grpc.aio.insecure_channel(f"127.0.0.1:{port}") as channel:
        stub = dagmanager_pb2_grpc.DiffServiceStub(channel)
        request = dagmanager_pb2.DiffRequest(strategy_id="s", dag_json="{}")
        [_ async for _ in stub.Diff(request)]
    await server.stop(None)

    assert captured["type"] == "diff"
    assert captured["specversion"] == "1.0"
    assert captured["data"]["strategy_id"] == "s"


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

    driver = FakeDriver()
    admin = FakeAdmin()
    stream = FakeStream()
    server, port = serve(driver, admin, stream, host="127.0.0.1", port=0, gc=gc)
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

    driver = FakeDriver()
    admin = FakeAdmin()
    stream = FakeStream()
    server, port = serve(driver, admin, stream, host="127.0.0.1", port=0, gc=gc)
    await server.start()
    async with grpc.aio.insecure_channel(f"127.0.0.1:{port}") as channel:
        stub = dagmanager_pb2_grpc.AdminServiceStub(channel)
        await stub.Cleanup(dagmanager_pb2.CleanupRequest(strategy_id="s"))
    await server.stop(None)

    assert store.dropped == ["s"]
    assert archive.archived == ["s"]


@pytest.mark.asyncio
async def test_grpc_tag_query():
    driver = FakeDriver()
    driver.session_obj = FakeSession([{"topic": "q1"}, {"topic": "q2"}])
    admin = FakeAdmin()
    stream = FakeStream()
    server, port = serve(driver, admin, stream, host="127.0.0.1", port=0)
    await server.start()
    async with grpc.aio.insecure_channel(f"127.0.0.1:{port}") as channel:
        stub = dagmanager_pb2_grpc.TagQueryStub(channel)
        req = dagmanager_pb2.TagQueryRequest(tags=["t"], interval=60)
        resp = await stub.GetQueues(req)
    await server.stop(None)
    assert list(resp.queues) == ["q1", "q2"]


@pytest.mark.asyncio
async def test_grpc_queue_stats():
    driver = FakeDriver()
    admin = FakeAdmin({"topic1": {"size": 3}})
    stream = FakeStream()
    server, port = serve(driver, admin, stream, host="127.0.0.1", port=0)
    await server.start()
    async with grpc.aio.insecure_channel(f"127.0.0.1:{port}") as channel:
        stub = dagmanager_pb2_grpc.AdminServiceStub(channel)
        resp = await stub.GetQueueStats(dagmanager_pb2.QueueStatsRequest(filter=""))
    await server.stop(None)
    assert resp.sizes["topic1"] == 3
