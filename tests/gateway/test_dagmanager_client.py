import pytest
import grpc
from types import SimpleNamespace

from qmtl.gateway.dagmanager_client import DagManagerClient
from qmtl.proto import dagmanager_pb2_grpc

class DummyChannel:
    def __init__(self):
        self.closed = False
    async def close(self):
        self.closed = True

@pytest.mark.asyncio
async def test_close_closes_channel(monkeypatch):
    chan = DummyChannel()
    monkeypatch.setattr(grpc.aio, "insecure_channel", lambda target: chan)
    monkeypatch.setattr(dagmanager_pb2_grpc, "DiffServiceStub", lambda c: None)
    monkeypatch.setattr(dagmanager_pb2_grpc, "TagQueryStub", lambda c: None)
    monkeypatch.setattr(dagmanager_pb2_grpc, "HealthCheckStub", lambda c: None)
    client = DagManagerClient("dummy")
    # ensure channel is created before closing
    await client.status()
    await client.close()
    assert chan.closed is True


@pytest.mark.asyncio
async def test_get_queues_by_tag_namespaces_by_default(monkeypatch):
    monkeypatch.delenv("QMTL_ENABLE_TOPIC_NAMESPACE", raising=False)
    client = DagManagerClient("dummy")
    client._ensure_channel = lambda: None

    class Stub:
        def __init__(self):
            self.calls = 0

        async def GetQueues(self, request):
            self.calls += 1
            return SimpleNamespace(
                queues=[SimpleNamespace(**{"queue": "foo", "global": False})]
            )

    stub = Stub()
    client._tag_stub = stub

    queues = await client.get_queues_by_tag(
        ["tag"],
        60,
        world_id="World-1",
        execution_domain="Paper",
    )

    assert stub.calls == 1
    assert queues == [
        {"queue": "world-1.paper.foo", "global": False},
    ]
    await client.close()


@pytest.mark.asyncio
async def test_get_queues_by_tag_respects_disable(monkeypatch):
    monkeypatch.setenv("QMTL_ENABLE_TOPIC_NAMESPACE", "0")
    client = DagManagerClient("dummy")
    client._ensure_channel = lambda: None

    class Stub:
        async def GetQueues(self, request):
            return SimpleNamespace(
                queues=[SimpleNamespace(**{"queue": "foo", "global": False})]
            )

    client._tag_stub = Stub()

    queues = await client.get_queues_by_tag(
        ["tag"],
        60,
        world_id="World-1",
        execution_domain="Paper",
    )

    assert queues == [
        {"queue": "foo", "global": False},
    ]
    await client.close()
