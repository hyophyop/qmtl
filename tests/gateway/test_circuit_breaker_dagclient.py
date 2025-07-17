import asyncio
import pytest
import grpc

from qmtl.gateway.dagmanager_client import DagManagerClient
from qmtl.gateway import metrics
from qmtl.proto import dagmanager_pb2, dagmanager_pb2_grpc


class DummyChannel:
    async def close(self):
        pass


def make_diff_stub(total_failures: int = 0):
    call_count = 0

    async def gen():
        yield dagmanager_pb2.DiffChunk()

    class Stub:
        def __init__(self, channel):
            pass

        def Diff(self, request):
            nonlocal call_count
            call_count += 1
            if call_count <= total_failures:
                raise grpc.RpcError("fail")
            return gen()

    return Stub


def make_tag_stub(total_failures: int = 0):
    call_count = 0

    class Stub:
        def __init__(self, channel):
            pass

        async def GetQueues(self, request):
            nonlocal call_count
            call_count += 1
            if call_count <= total_failures:
                raise grpc.RpcError("fail")
            return dagmanager_pb2.TagQueryReply(queues=["q"])

    return Stub


def make_health_stub(total_failures: int = 0):
    call_count = 0

    class Stub:
        def __init__(self, channel):
            pass

        async def Status(self, request):
            nonlocal call_count
            call_count += 1
            if call_count <= total_failures:
                raise grpc.RpcError("fail")
            return dagmanager_pb2.StatusReply(neo4j="ok", state="running")

    return Stub


@pytest.mark.asyncio
async def test_breaker_opens_and_resets(monkeypatch):
    DiffStub = make_diff_stub(total_failures=10)
    TagStub = make_tag_stub()
    HealthStub = make_health_stub()
    monkeypatch.setattr(dagmanager_pb2_grpc, "DiffServiceStub", DiffStub)
    monkeypatch.setattr(dagmanager_pb2_grpc, "TagQueryStub", TagStub)
    monkeypatch.setattr(dagmanager_pb2_grpc, "HealthCheckStub", HealthStub)
    monkeypatch.setattr(grpc.aio, "insecure_channel", lambda target: DummyChannel())

    metrics.reset_metrics()
    client = DagManagerClient("dummy", breaker_max_failures=2, breaker_reset_timeout=0.05)

    for _ in range(2):
        with pytest.raises(grpc.RpcError):
            await client.diff("s", "{}")
    assert client.breaker.is_open
    assert metrics.dagclient_breaker_state._value.get() == 1
    assert metrics.dagclient_breaker_failures._value.get() == 2
    assert metrics.dagclient_breaker_open_total._value.get() == 1  # type: ignore[attr-defined]

    with pytest.raises(RuntimeError):
        await client.diff("s", "{}")

    await asyncio.sleep(0.06)
    assert not client.breaker.is_open
    result = await client.diff("s", "{}")
    assert isinstance(result, dagmanager_pb2.DiffChunk)
    assert metrics.dagclient_breaker_state._value.get() == 0
    assert metrics.dagclient_breaker_failures._value.get() == 0
    await client.close()


@pytest.mark.asyncio
async def test_get_queues_uses_breaker(monkeypatch):
    DiffStub = make_diff_stub()
    TagStub = make_tag_stub(total_failures=10)
    HealthStub = make_health_stub()
    monkeypatch.setattr(dagmanager_pb2_grpc, "DiffServiceStub", DiffStub)
    monkeypatch.setattr(dagmanager_pb2_grpc, "TagQueryStub", TagStub)
    monkeypatch.setattr(dagmanager_pb2_grpc, "HealthCheckStub", HealthStub)
    monkeypatch.setattr(grpc.aio, "insecure_channel", lambda target: DummyChannel())

    metrics.reset_metrics()
    client = DagManagerClient("dummy", breaker_max_failures=2, breaker_reset_timeout=0.05)

    for _ in range(2):
        with pytest.raises(grpc.RpcError):
            await client.get_queues_by_tag(["t"], 60)
    with pytest.raises(RuntimeError):
        await client.get_queues_by_tag(["t"], 60)
    assert metrics.dagclient_breaker_state._value.get() == 1
    assert metrics.dagclient_breaker_open_total._value.get() == 1  # type: ignore[attr-defined]
    await client.close()


@pytest.mark.asyncio
async def test_status_uses_breaker(monkeypatch):
    DiffStub = make_diff_stub()
    TagStub = make_tag_stub()
    HealthStub = make_health_stub(total_failures=2)
    monkeypatch.setattr(dagmanager_pb2_grpc, "DiffServiceStub", DiffStub)
    monkeypatch.setattr(dagmanager_pb2_grpc, "TagQueryStub", TagStub)
    monkeypatch.setattr(dagmanager_pb2_grpc, "HealthCheckStub", HealthStub)
    monkeypatch.setattr(grpc.aio, "insecure_channel", lambda target: DummyChannel())

    metrics.reset_metrics()
    client = DagManagerClient("dummy", breaker_max_failures=2, breaker_reset_timeout=0.05)

    assert await client.status() is False
    assert await client.status() is False
    assert client.breaker.is_open
    assert metrics.dagclient_breaker_state._value.get() == 1
    assert metrics.dagclient_breaker_open_total._value.get() == 1  # type: ignore[attr-defined]
    assert await client.status() is False
    await asyncio.sleep(0.06)
    assert await client.status() is True
    assert metrics.dagclient_breaker_state._value.get() == 0
    assert metrics.dagclient_breaker_failures._value.get() == 0
    await client.close()
