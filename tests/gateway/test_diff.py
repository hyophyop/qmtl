import asyncio
import pytest
import grpc

from qmtl.gateway.dagmanager_client import DagManagerClient
from qmtl.proto import dagmanager_pb2, dagmanager_pb2_grpc
from qmtl.dagmanager.kafka_admin import partition_key, compute_key


class DummyChannel:
    async def close(self):
        pass


def make_stub(chunks, fail_times=0):
    call_count = 0
    ack_count = 0

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
            nonlocal ack_count
            ack_count += 1
            return ack

    return Stub, lambda: call_count, lambda: ack_count


def _queue_key(node_id: str) -> str:
    return partition_key(node_id, None, None, compute_key=compute_key(node_id))


@pytest.mark.asyncio
async def test_diff_collects_chunks(monkeypatch):
    chunks = [
        dagmanager_pb2.DiffChunk(
            queue_map={_queue_key("A"): "topic_a"}, sentinel_id="s"
        ),
        dagmanager_pb2.DiffChunk(
            queue_map={_queue_key("B"): "topic_b"}, sentinel_id="s"
        ),
    ]
    Stub, _, get_acks = make_stub(chunks)
    monkeypatch.setattr(dagmanager_pb2_grpc, "DiffServiceStub", Stub)
    monkeypatch.setattr(dagmanager_pb2_grpc, "TagQueryStub", lambda c: None)
    monkeypatch.setattr(dagmanager_pb2_grpc, "HealthCheckStub", lambda c: None)
    monkeypatch.setattr(grpc.aio, "insecure_channel", lambda target: DummyChannel())

    client = DagManagerClient("127.0.0.1:1")
    result = await client.diff("sid", "{}")
    assert result.queue_map == {
        _queue_key("A"): "topic_a",
        _queue_key("B"): "topic_b",
    }
    assert result.sentinel_id == "s"
    assert get_acks() == 2
    await client.close()


@pytest.mark.asyncio
async def test_diff_returns_buffer_nodes(monkeypatch):
    chunks = [
        dagmanager_pb2.DiffChunk(
            queue_map={_queue_key("A"): "topic_a"},
            sentinel_id="s",
            buffer_nodes=[dagmanager_pb2.BufferInstruction(node_id="A", lag=5)],
        )
    ]
    Stub, _, get_acks = make_stub(chunks)
    monkeypatch.setattr(dagmanager_pb2_grpc, "DiffServiceStub", Stub)
    monkeypatch.setattr(dagmanager_pb2_grpc, "TagQueryStub", lambda c: None)
    monkeypatch.setattr(dagmanager_pb2_grpc, "HealthCheckStub", lambda c: None)
    monkeypatch.setattr(grpc.aio, "insecure_channel", lambda target: DummyChannel())

    client = DagManagerClient("127.0.0.1:1")
    result = await client.diff("sid", "{}")
    assert [b.node_id for b in result.buffer_nodes] == ["A"]
    assert result.buffer_nodes[0].lag == 5
    assert get_acks() == 1
    await client.close()


@pytest.mark.asyncio
async def test_diff_retries(monkeypatch):
    chunk = dagmanager_pb2.DiffChunk(queue_map={_queue_key("A"): "t"}, sentinel_id="s")
    Stub, get_calls, get_acks = make_stub([chunk], fail_times=2)
    monkeypatch.setattr(dagmanager_pb2_grpc, "DiffServiceStub", Stub)
    monkeypatch.setattr(dagmanager_pb2_grpc, "TagQueryStub", lambda c: None)
    monkeypatch.setattr(dagmanager_pb2_grpc, "HealthCheckStub", lambda c: None)
    monkeypatch.setattr(grpc.aio, "insecure_channel", lambda target: DummyChannel())
    async def _nowait(self, timeout: float = 5.0) -> None:
        return None
    monkeypatch.setattr(DagManagerClient, "_wait_for_service", _nowait)

    client = DagManagerClient("127.0.0.1:1")
    result = await client.diff("sid", "{}")
    assert result.queue_map == {_queue_key("A"): "t"}
    assert get_calls() == 3
    assert get_acks() == 1
    await client.close()
