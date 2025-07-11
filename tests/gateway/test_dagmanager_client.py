import pytest
import grpc

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
    await client.close()
    assert chan.closed is True
