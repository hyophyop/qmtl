import json

import pytest
import grpc

from qmtl.services.gateway.dagmanager_client import DagManagerClient
from qmtl.foundation.proto import dagmanager_pb2, dagmanager_pb2_grpc
from qmtl.services.dagmanager.topic import (
    set_topic_namespace_enabled,
    topic_namespace_enabled,
)


class FakeDiffStub:
    def __init__(self, chunks: list[dagmanager_pb2.DiffChunk]) -> None:
        self.chunks = chunks
        self.acks: list[tuple[str, int]] = []
        self.calls = 0

    async def Diff(self, request):  # pragma: no cover - exercised via client
        self.calls += 1
        for chunk in self.chunks:
            yield chunk

    async def AckChunk(self, ack: dagmanager_pb2.ChunkAck):
        self.acks.append((ack.sentinel_id, ack.chunk_id))

class DummyChannel:
    def __init__(self):
        self.closed = False
    async def close(self):
        self.closed = True


@pytest.fixture(autouse=True)
def reset_topic_namespace():
    previous = topic_namespace_enabled()
    yield
    set_topic_namespace_enabled(previous)

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
async def test_diff_applies_namespace_and_acknowledges_chunks():
    set_topic_namespace_enabled(True)
    chunk = dagmanager_pb2.DiffChunk(
        queue_map={"queue": "topic"}, sentinel_id="s1", crc32=42
    )
    diff_stub = FakeDiffStub([chunk])
    client = DagManagerClient("dummy")
    client._diff_stub = diff_stub
    client._ensure_channel = lambda: None

    async def _wait_for_service(timeout: float = 5.0):  # pragma: no cover - noop
        return None

    client._wait_for_service = _wait_for_service

    result = await client.diff(
        "sid",
        json.dumps({"meta": {"topic_namespace": "alpha.beta"}}),
        world_id="w",
        execution_domain="live",
    )

    assert result is not None
    assert result.queue_map == {"queue": "alpha.beta.topic"}
    assert diff_stub.acks == [("s1", 0)]


@pytest.mark.asyncio
async def test_diff_returns_none_on_crc_mismatch():
    set_topic_namespace_enabled(False)
    chunks = [
        dagmanager_pb2.DiffChunk(queue_map={"queue": "topic"}, sentinel_id="s1", crc32=1),
        dagmanager_pb2.DiffChunk(queue_map={}, sentinel_id="s1", crc32=2),
    ]
    diff_stub = FakeDiffStub(chunks)
    client = DagManagerClient("dummy", breaker_max_failures=1)
    client._diff_stub = diff_stub
    client._ensure_channel = lambda: None

    async def _wait_for_service(timeout: float = 5.0):  # pragma: no cover - noop
        return None

    client._wait_for_service = _wait_for_service

    result = await client.diff("sid", "{}", world_id=None, execution_domain=None)

    assert result is None
    assert client.breaker.failures >= 1
    assert diff_stub.acks  # at least one acknowledgement attempted
