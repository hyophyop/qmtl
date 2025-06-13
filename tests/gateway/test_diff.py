import asyncio
import pytest
import grpc

from qmtl.gateway.dagmanager_client import DagManagerClient
from qmtl.proto import dagmanager_pb2, dagmanager_pb2_grpc


class DummyChannel:
    async def close(self):
        pass


def make_stub(chunks, fail_times=0):
    call_count = 0

    async def gen():
        for c in chunks:
            yield c

    class Stub:
        def __init__(self, channel):
            pass

        def Diff(self, request):
            nonlocal call_count
            call_count += 1
            if call_count <= fail_times:
                raise grpc.RpcError("fail")
            return gen()

        async def AckChunk(self, ack):
            return ack

    return Stub, lambda: call_count


@pytest.mark.asyncio
async def test_diff_collects_chunks(monkeypatch):
    chunks = [
        dagmanager_pb2.DiffChunk(queue_map={"A": "topic_a"}, sentinel_id="s"),
        dagmanager_pb2.DiffChunk(queue_map={"B": "topic_b"}, sentinel_id="s"),
    ]
    Stub, _ = make_stub(chunks)
    monkeypatch.setattr(dagmanager_pb2_grpc, "DiffServiceStub", Stub)
    monkeypatch.setattr(grpc.aio, "insecure_channel", lambda target: DummyChannel())

    client = DagManagerClient("127.0.0.1:1")
    result = await client.diff("sid", "{}")
    assert result.queue_map == {"A": "topic_a", "B": "topic_b"}
    assert result.sentinel_id == "s"


@pytest.mark.asyncio
async def test_diff_returns_buffer_nodes(monkeypatch):
    chunks = [
        dagmanager_pb2.DiffChunk(
            queue_map={"A": "topic_a"},
            sentinel_id="s",
            buffer_nodes=[dagmanager_pb2.BufferInstruction(node_id="A", lag=5)]
        )
    ]
    Stub, _ = make_stub(chunks)
    monkeypatch.setattr(dagmanager_pb2_grpc, "DiffServiceStub", Stub)
    monkeypatch.setattr(grpc.aio, "insecure_channel", lambda target: DummyChannel())

    client = DagManagerClient("127.0.0.1:1")
    result = await client.diff("sid", "{}")
    assert [b.node_id for b in result.buffer_nodes] == ["A"]
    assert result.buffer_nodes[0].lag == 5


@pytest.mark.asyncio
async def test_diff_retries(monkeypatch):
    chunk = dagmanager_pb2.DiffChunk(queue_map={"A": "t"}, sentinel_id="s")
    Stub, get_calls = make_stub([chunk], fail_times=2)
    monkeypatch.setattr(dagmanager_pb2_grpc, "DiffServiceStub", Stub)
    monkeypatch.setattr(grpc.aio, "insecure_channel", lambda target: DummyChannel())
    orig_sleep = asyncio.sleep
    monkeypatch.setattr(asyncio, "sleep", lambda t: orig_sleep(0))

    client = DagManagerClient("127.0.0.1:1")
    result = await client.diff("sid", "{}")
    assert result.queue_map == {"A": "t"}
    assert get_calls() == 3
