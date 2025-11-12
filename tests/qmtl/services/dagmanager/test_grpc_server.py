import asyncio
from collections import deque
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
from qmtl.services.gateway.controlbus_consumer import ControlBusConsumer, ControlBusMessage


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
async def test_grpc_diff_ack_timeout_recovery(monkeypatch):
    from qmtl.services.dagmanager import grpc_server as grpc_mod

    plan_template = [AckStatus.OK, AckStatus.TIMEOUT, AckStatus.OK]
    resume_calls = 0

    original_init = grpc_mod._GrpcStream.__init__

    def patched_init(self, loop):
        original_init(self, loop)
        self._test_ack_plan = deque(plan_template)

    monkeypatch.setattr(grpc_mod._GrpcStream, "__init__", patched_init)

    original_wait = grpc_mod._GrpcStream.wait_for_ack

    def patched_wait(self):
        plan = getattr(self, "_test_ack_plan", None)
        if plan:
            status = plan[0]
            if status is AckStatus.TIMEOUT:
                plan.popleft()
                with self._ack_lock:
                    self._last_ack = AckStatus.TIMEOUT
                return self._last_ack
            plan.popleft()
        return original_wait(self)

    monkeypatch.setattr(grpc_mod._GrpcStream, "wait_for_ack", patched_wait)

    original_resume = grpc_mod._GrpcStream.resume_from_last_offset

    def patched_resume(self):
        nonlocal resume_calls
        resume_calls += 1
        return original_resume(self)

    monkeypatch.setattr(
        grpc_mod._GrpcStream, "resume_from_last_offset", patched_resume
    )

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

    sentinel_ids: set[str] = set()
    chunk_sizes: list[int] = []
    second_chunk_seen = 0
    acked = 0

    try:
        async with grpc.aio.insecure_channel(f"127.0.0.1:{port}") as channel:
            stub = dagmanager_pb2_grpc.DiffServiceStub(channel)
            request = dagmanager_pb2.DiffRequest(strategy_id="s", dag_json=dag_json)
            async for chunk in stub.Diff(request):
                sentinel_ids.add(chunk.sentinel_id)
                chunk_sizes.append(len(chunk.queue_map))
                if len(chunk_sizes) == 1:
                    await stub.AckChunk(
                        dagmanager_pb2.ChunkAck(
                            sentinel_id=chunk.sentinel_id, chunk_id=0
                        )
                    )
                    acked += 1
                    continue

                second_chunk_seen += 1
                if second_chunk_seen == 1:
                    expected_queue_map = dict(chunk.queue_map)
                    continue

                assert dict(chunk.queue_map) == expected_queue_map
                await stub.AckChunk(
                    dagmanager_pb2.ChunkAck(
                        sentinel_id=chunk.sentinel_id, chunk_id=0
                    )
                )
                acked += 1
    finally:
        await server.stop(None)

    assert acked == 2
    assert second_chunk_seen == 2, "chunk should be replayed after timeout"
    assert resume_calls == 1
    assert sentinel_ids == {"s-sentinel"}
    # every chunk carries the full queue map, ensure it covers all nodes
    assert chunk_sizes and chunk_sizes[-1] == len(nodes)


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


class BusStub:
    def __init__(self) -> None:
        self.queue_updates: list[tuple[list[str], int, list[object], str]] = []

    async def publish_queue_update(
        self,
        tags,
        interval,
        queues,
        match_mode: str = "any",
        *,
        version: int = 1,
    ) -> None:
        self.queue_updates.append((list(tags), int(interval), list(queues), match_mode))

    async def publish_sentinel_weight(self, *args, **kwargs):  # pragma: no cover - unused
        pass


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
async def test_grpc_cleanup_emits_queue_update():
    now = datetime.now(UTC)
    store = DummyStore([QueueInfo("q", "raw", now - timedelta(days=10), interval=60)])
    gc = GarbageCollector(store, DummyMetrics(), batch_size=1)
    bus = BusStub()

    driver = FakeDriver()
    admin = FakeAdmin()
    stream = FakeStream()
    server, port = serve(
        driver,
        admin,
        stream,
        host="127.0.0.1",
        port=0,
        gc=gc,
        bus=bus,
    )
    await server.start()
    async with grpc.aio.insecure_channel(f"127.0.0.1:{port}") as channel:
        stub = dagmanager_pb2_grpc.AdminServiceStub(channel)
        await stub.Cleanup(dagmanager_pb2.CleanupRequest(strategy_id="s"))
    await server.stop(None)

    assert bus.queue_updates == [(["raw"], 60, [], "any")]


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


@pytest.mark.asyncio
async def test_grpc_diff_emits_sentinel_weight_and_gateway_consumes():
    driver = FakeDriver()
    admin = FakeAdmin()
    stream = FakeStream()
    producer = DummyProducer()
    bus = ControlBusProducer(producer=producer, topic="queue")
    server, port = serve(driver, admin, stream, host="127.0.0.1", port=0, bus=bus)
    await server.start()

    sentinel_msgs: list[tuple[str, bytes, bytes | None]] = []
    try:
        async with grpc.aio.insecure_channel(f"127.0.0.1:{port}") as channel:
            stub = dagmanager_pb2_grpc.DiffServiceStub(channel)

            async def run_diff(weight: float) -> None:
                dag_json = json.dumps(
                    {
                        "nodes": [
                            {
                                "node_id": "n1",
                                "node_type": "Compute",
                                "code_hash": "c",
                                "config_hash": "cfg",
                                "schema_hash": "s",
                                "schema_compat_id": "s-major",
                                "params": {},
                                "dependencies": [],
                                "interval": 60,
                                "tags": ["x"],
                            },
                            {
                                "node_type": "VersionSentinel",
                                "node_id": "s-sentinel",
                                "traffic_weight": weight,
                                "version": "v1",
                            },
                        ]
                    }
                )
                request = dagmanager_pb2.DiffRequest(strategy_id="s", dag_json=dag_json)
                async for chunk in stub.Diff(request):
                    await stub.AckChunk(
                        dagmanager_pb2.ChunkAck(sentinel_id=chunk.sentinel_id, chunk_id=0)
                    )

            await run_diff(0.25)
            sentinel_msgs = [entry for entry in producer.sent if entry[0] == "sentinel_weight"]
            assert len(sentinel_msgs) == 1

            await run_diff(0.25)
            sentinel_msgs = [entry for entry in producer.sent if entry[0] == "sentinel_weight"]
            assert len(sentinel_msgs) == 1

            await run_diff(0.75)
            sentinel_msgs = [entry for entry in producer.sent if entry[0] == "sentinel_weight"]
            assert len(sentinel_msgs) == 2
    finally:
        await server.stop(None)

    topic, data, key = sentinel_msgs[-1]
    assert topic == "sentinel_weight"
    assert key == b"s-sentinel"
    payload = json.loads(data.decode())
    assert payload["sentinel_id"] == "s-sentinel"
    assert payload["weight"] == pytest.approx(0.75)
    assert payload["version"] == 1
    assert payload["etag"].startswith("sw:s-sentinel")
    assert payload["ts"].endswith("Z")
    assert payload.get("sentinel_version") == "v1"

    class SentinelHub:
        def __init__(self) -> None:
            self.events: list[tuple[str, float]] = []

        async def send_sentinel_weight(self, sentinel_id: str, weight: float) -> None:
            self.events.append((sentinel_id, weight))

    hub = SentinelHub()
    consumer = ControlBusConsumer(brokers=[], topics=["sentinel_weight"], group="g", ws_hub=hub)
    message = ControlBusMessage(
        topic="sentinel_weight",
        key="s-sentinel",
        etag=payload.get("etag", ""),
        run_id="",
        data=payload,
        timestamp_ms=None,
    )
    await consumer._handle_message(message)
    assert len(hub.events) == 1
    sid, weight = hub.events[0]
    assert sid == "s-sentinel"
    assert weight == pytest.approx(0.75)
