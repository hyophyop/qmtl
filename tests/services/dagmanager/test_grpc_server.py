import asyncio
from datetime import datetime, timedelta, UTC

import grpc
import pytest

pytestmark = [
    pytest.mark.filterwarnings('ignore::pytest.PytestUnraisableExceptionWarning'),
    pytest.mark.filterwarnings('ignore:unclosed <socket.socket[^>]*>'),
    pytest.mark.filterwarnings('ignore:unclosed event loop'),
]
import json

from qmtl.services.dagmanager.diff_service import StreamSender
from qmtl.services.dagmanager.kafka_admin import TopicExistsError, partition_key, compute_key
from qmtl.services.dagmanager.grpc_server import serve
from qmtl.services.dagmanager.api import create_app
from qmtl.services.dagmanager import metrics
from qmtl.services.dagmanager.garbage_collector import GarbageCollector, QueueInfo
from qmtl.foundation.proto import dagmanager_pb2, dagmanager_pb2_grpc
from qmtl.services.dagmanager.monitor import AckStatus
from qmtl.services.dagmanager.controlbus_producer import ControlBusProducer


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
        if name in self.topics:
            raise TopicExistsError
        self.created.append((name, num_partitions, replication_factor, config))
        self.topics[name] = {
            "config": dict(config or {}),
            "num_partitions": num_partitions,
            "replication_factor": replication_factor,
        }


class FakeStream(StreamSender):
    def send(self, chunk):
        pass

    def wait_for_ack(self) -> AckStatus:
        return AckStatus.OK

    def ack(self, status: AckStatus = AckStatus.OK):
        pass


class DummyGC:
    def collect(self):
        return []


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
        {
            "node_id": str(i),
            "node_type": "N",
            "code_hash": "c",
            "config_hash": "cfg",
            "schema_hash": "s",
            "schema_compat_id": "s-major",
            "params": {},
            "dependencies": [],
        }
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

    from qmtl.services.dagmanager.diff_service import DiffChunk, DiffRequest

    class DummyDiff:
        def __init__(self, *a, **k):
            pass

        def diff(self, request: DiffRequest):
            called["sid"] = request.strategy_id
            return DiffChunk(
                queue_map={
                    partition_key(
                        "x",
                        None,
                        None,
                        compute_key=compute_key(
                            "x",
                            world_id=request.world_id,
                            execution_domain=request.execution_domain,
                            as_of=request.as_of,
                            partition=request.partition,
                            dataset_fingerprint=request.dataset_fingerprint,
                        ),
                    ): "t"
                },
                sentinel_id=request.strategy_id + "-sentinel",
                version="v1",
                crc32=0,
            )

        async def diff_async(self, request: DiffRequest):
            return self.diff(request)

    monkeypatch.setattr("qmtl.services.dagmanager.grpc_server.DiffService", DummyDiff)

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
    key = partition_key(
        "x",
        None,
        None,
        compute_key=compute_key("x"),
    )
    assert dict(resp.queue_map)[key] == "t"
    assert resp.sentinel_id == "v2-sentinel"


@pytest.mark.asyncio
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
    assert [q.queue for q in resp.queues] == ["q1", "q2"]


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


class DummyProducer:
    def __init__(self) -> None:
        self.sent: list[tuple[str, bytes, bytes | None]] = []

    async def send_and_wait(self, topic, data, key=None):
        self.sent.append((topic, data, key))


@pytest.mark.asyncio
async def test_grpc_diff_publishes_controlbus():
    driver = FakeDriver()
    admin = FakeAdmin()
    stream = FakeStream()
    producer = DummyProducer()
    bus = ControlBusProducer(producer=producer, topic="queue")
    server, port = serve(driver, admin, stream, host="127.0.0.1", port=0, bus=bus)
    await server.start()
    dag_json = json.dumps(
        {
            "nodes": [
                {
                    "node_id": "n1",
                    "node_type": "N",
                    "code_hash": "c",
                    "config_hash": "cfg",
                    "schema_hash": "s",
                    "schema_compat_id": "s-major",
                    "params": {},
                    "dependencies": [],
                    "interval": 60,
                    "tags": ["x"],
                }
            ]
        }
    )
    async with grpc.aio.insecure_channel(f"127.0.0.1:{port}") as channel:
        stub = dagmanager_pb2_grpc.DiffServiceStub(channel)
        request = dagmanager_pb2.DiffRequest(strategy_id="s", dag_json=dag_json)
        async for chunk in stub.Diff(request):
            await stub.AckChunk(
                dagmanager_pb2.ChunkAck(sentinel_id=chunk.sentinel_id, chunk_id=0)
            )
    await server.stop(None)
    assert producer.sent
    topic, data, key = producer.sent[0]
    assert topic == "queue"
    payload = json.loads(data.decode())
    assert payload["tags"] == ["x"]
