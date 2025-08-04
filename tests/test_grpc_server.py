import asyncio
from datetime import datetime, timedelta, UTC

import grpc
import pytest
import httpx
import json

from qmtl.dagmanager.diff_service import StreamSender
from qmtl.dagmanager.grpc_server import serve
from qmtl.dagmanager.http_server import create_app
from qmtl.dagmanager import metrics
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

    def wait_for_ack(self):
        pass

    def ack(self):
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
        responses = []
        async for chunk in stub.Diff(request):
            responses.append(chunk)
            await stub.AckChunk(
                dagmanager_pb2.ChunkAck(sentinel_id=chunk.sentinel_id, chunk_id=0)
            )
    await server.stop(None)
    assert responses[0].sentinel_id == "s-sentinel"


@pytest.mark.asyncio
async def test_grpc_diff_multiple_chunks():
    driver = FakeDriver()
    admin = FakeAdmin()
    stream = FakeStream()
    server, port = serve(driver, admin, stream, host="127.0.0.1", port=0)
    await server.start()
    nodes = [
        {"node_id": str(i), "node_type": "N", "code_hash": "c", "schema_hash": "s"}
        for i in range(120)
    ]
    dag_json = json.dumps({"nodes": nodes})
    async with grpc.aio.insecure_channel(f"127.0.0.1:{port}") as channel:
        stub = dagmanager_pb2_grpc.DiffServiceStub(channel)
        request = dagmanager_pb2.DiffRequest(strategy_id="s", dag_json=dag_json)
        count = 0
        async for chunk in stub.Diff(request):
            count += 1
            await stub.AckChunk(
                dagmanager_pb2.ChunkAck(sentinel_id=chunk.sentinel_id, chunk_id=0)
            )
    await server.stop(None)
    assert count == 2


@pytest.mark.asyncio
async def test_grpc_diff_no_nodes():
    driver = FakeDriver()
    admin = FakeAdmin()
    stream = FakeStream()
    server, port = serve(driver, admin, stream, host="127.0.0.1", port=0)
    await server.start()
    async with grpc.aio.insecure_channel(f"127.0.0.1:{port}") as channel:
        stub = dagmanager_pb2_grpc.DiffServiceStub(channel)
        req = dagmanager_pb2.DiffRequest(strategy_id="s", dag_json="{}")
        received = []
        async for chunk in stub.Diff(req):
            received.append(chunk)
            await stub.AckChunk(
                dagmanager_pb2.ChunkAck(sentinel_id=chunk.sentinel_id, chunk_id=0)
            )
    await server.stop(None)
    assert received and received[0].sentinel_id == "s-sentinel"


@pytest.mark.asyncio
async def test_grpc_redo_diff(monkeypatch):
    called = {}

    from qmtl.dagmanager.diff_service import DiffChunk, DiffRequest

    class DummyDiff:
        def __init__(self, *a, **k):
            pass

        def diff(self, request: DiffRequest):
            called["sid"] = request.strategy_id
            return DiffChunk(
                queue_map={"x": "t"}, sentinel_id=request.strategy_id + "-sentinel"
            )

        async def diff_async(self, request: DiffRequest):
            return self.diff(request)

    monkeypatch.setattr("qmtl.dagmanager.grpc_server.DiffService", DummyDiff)

    driver = FakeDriver()
    admin = FakeAdmin()
    stream = FakeStream()
    server, port = serve(driver, admin, stream, host="127.0.0.1", port=0)
    await server.start()
    async with grpc.aio.insecure_channel(f"127.0.0.1:{port}") as channel:
        stub = dagmanager_pb2_grpc.AdminServiceStub(channel)
        req = dagmanager_pb2.RedoDiffRequest(sentinel_id="v2", dag_json="{}")
        resp = await stub.RedoDiff(req)
    await server.stop(None)

    assert called["sid"] == "v2"
    assert dict(resp.queue_map)["x"] == "t"
    assert resp.sentinel_id == "v2-sentinel"


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
        "qmtl.dagmanager.grpc_server.post",
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
        dag_json = json.dumps(
            {
                "nodes": [
                    {
                        "node_id": "n1",
                        "node_type": "N",
                        "code_hash": "c",
                        "schema_hash": "s",
                        "interval": 60,
                        "tags": ["x"],
                    }
                ]
            }
        )
        request = dagmanager_pb2.DiffRequest(strategy_id="s", dag_json=dag_json)
        async for chunk in stub.Diff(request):
            await stub.AckChunk(
                dagmanager_pb2.ChunkAck(sentinel_id=chunk.sentinel_id, chunk_id=0)
            )
    await server.stop(None)

    assert captured["type"] == "queue_update"
    assert captured["specversion"] == "1.0"
    assert captured["data"]["tags"] == ["x"]


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
    now = datetime.now(UTC)
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
    now = datetime.now(UTC)
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
    driver.session_obj = FakeSession([{"topic": "topic1"}])
    admin = FakeAdmin({"topic1": {"size": 3}, "topic2": {"size": 5}})
    stream = FakeStream()
    server, port = serve(driver, admin, stream, host="127.0.0.1", port=0)
    await server.start()
    async with grpc.aio.insecure_channel(f"127.0.0.1:{port}") as channel:
        stub = dagmanager_pb2_grpc.AdminServiceStub(channel)
        req = dagmanager_pb2.QueueStatsRequest(filter="tag=t;interval=60")
        resp = await stub.GetQueueStats(req)
    await server.stop(None)
    assert dict(resp.sizes) == {"topic1": 3}


@pytest.mark.asyncio
async def test_http_sentinel_traffic(monkeypatch):
    metrics.reset_metrics()
    weights: dict[str, float] = {}
    captured: dict = {}
    driver = FakeDriver()

    metrics.reset_metrics()

    async def mock_post(url, json, **_):
        captured.update(json)
        return httpx.Response(202)

    monkeypatch.setattr(
        "qmtl.dagmanager.http_server.post",
        mock_post,
    )

    app = create_app(weights=weights, gateway_url="http://gw", driver=driver)
    transport = httpx.ASGITransport(app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/callbacks/sentinel-traffic",
            json={"version": "v1", "weight": 0.7},
        )

    assert resp.status_code == 202
    assert weights["v1"] == 0.7
    assert captured["type"] == "sentinel_weight"
    assert captured["data"]["sentinel_id"] == "v1"
    assert captured["data"]["weight"] == 0.7
    assert metrics.dagmanager_active_version_weight._vals["v1"] == 0.7
    assert captured["type"] == "sentinel_weight"
    assert captured["data"]["sentinel_id"] == "v1"
    assert captured["data"]["weight"] == 0.7
    query, params = driver.session_obj.run_calls[0]
    assert "traffic_weight" in query
    assert params["version"] == "v1"
    assert params["weight"] == 0.7


@pytest.mark.asyncio
async def test_http_sentinel_traffic_overwrite():
    metrics.reset_metrics()
    weights = {"v1": 0.1}
    driver = FakeDriver()
    metrics.reset_metrics()
    app = create_app(weights=weights, driver=driver)
    transport = httpx.ASGITransport(app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            "/callbacks/sentinel-traffic",
            json={"version": "v1", "weight": 0.4},
        )
    assert weights["v1"] == 0.4
    assert metrics.dagmanager_active_version_weight._vals["v1"] == 0.4
    query, params = driver.session_obj.run_calls[0]
    assert params["version"] == "v1"
    assert params["weight"] == 0.4
