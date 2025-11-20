import asyncio
import pytest
import grpc

from qmtl.services.gateway.dagmanager_client import DagManagerClient
from qmtl.services.gateway import metrics
from qmtl.foundation.proto import dagmanager_pb2, dagmanager_pb2_grpc


@pytest.fixture(autouse=True)
def fast_delay(monkeypatch):
    """Eliminate asyncio sleep calls to speed up retries."""

    async def _fast_delay(delay, *args, **kwargs):
        return None

    monkeypatch.setattr(asyncio, "sleep", _fast_delay)


class DummyChannel:
    async def close(self):
        pass


def make_diff_stub(total_failures: int = 0):
    call_count = 0

    async def gen():
        yield dagmanager_pb2.DiffChunk(sentinel_id="s", crc32=0)

    class Stub:
        def __init__(self, channel):
            pass

        def Diff(self, request):
            nonlocal call_count
            call_count += 1
            if call_count <= total_failures:
                raise grpc.RpcError("fail")
            return gen()

        async def AckChunk(self, request):
            return None

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
    DiffStub = make_diff_stub(total_failures=5)
    HealthStub = make_health_stub()
    monkeypatch.setattr(dagmanager_pb2_grpc, "DiffServiceStub", DiffStub)
    monkeypatch.setattr(dagmanager_pb2_grpc, "HealthCheckStub", HealthStub)
    monkeypatch.setattr(grpc.aio, "insecure_channel", lambda target: DummyChannel())

    metrics.reset_metrics()
    client = DagManagerClient("dummy", breaker_max_failures=1)

    assert await client.diff("s", "{}") is None
    assert client.breaker.is_open

    client.breaker.reset()
    assert not client.breaker.is_open
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
    client = DagManagerClient("dummy", breaker_max_failures=2)

    for _ in range(2):
        assert await client.get_queues_by_tag(["t"], 60) == []
    assert await client.get_queues_by_tag(["t"], 60) == []
    assert metrics.dagclient_breaker_state._value.get() == 1
    assert int(metrics.dagclient_breaker_open_total._value.get()) == 1
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
    client = DagManagerClient("dummy", breaker_max_failures=2)

    assert await client.status() is False
    assert await client.status() is False
    assert client.breaker.is_open
    assert metrics.dagclient_breaker_state._value.get() == 1
    assert int(metrics.dagclient_breaker_open_total._value.get()) == 1
    assert await client.status() is False
    client.breaker.reset()
    assert await client.status() is True
    assert metrics.dagclient_breaker_state._value.get() == 0
    assert metrics.dagclient_breaker_failures._value.get() == 0
    await client.close()
