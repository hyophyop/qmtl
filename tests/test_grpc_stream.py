import asyncio
import pytest

from qmtl.dagmanager.grpc_server import _GrpcStream
from qmtl.dagmanager.diff_service import DiffChunk
from qmtl.dagmanager.monitor import AckStatus


@pytest.mark.asyncio
async def test_resume_requeues_unacked_chunks():
    stream = _GrpcStream(asyncio.get_running_loop())
    chunk = DiffChunk(queue_map={}, sentinel_id="s")

    stream.send(chunk)
    # Simulate client consuming the chunk
    assert await stream.queue.get() is chunk

    # No ACK received; resume should replay the chunk and reset status
    stream._last_ack = AckStatus.TIMEOUT  # simulate timeout
    stream.resume_from_last_offset()
    assert stream.ack_status() is AckStatus.OK
    assert await asyncio.wait_for(stream.queue.get(), timeout=0.1) is chunk


@pytest.mark.asyncio
async def test_resume_skips_acknowledged_chunks():
    stream = _GrpcStream(asyncio.get_running_loop())
    first = DiffChunk(queue_map={}, sentinel_id="s")
    second = DiffChunk(queue_map={}, sentinel_id="s")

    stream.send(first)
    await stream.queue.get()
    stream.ack()  # first chunk acknowledged

    stream.send(second)
    await stream.queue.get()
    # second chunk not acknowledged
    stream.resume_from_last_offset()

    # Only second chunk should be replayed
    assert await asyncio.wait_for(stream.queue.get(), timeout=0.1) is second

    # After acknowledging, resume should not replay anything
    stream.ack()
    stream.resume_from_last_offset()
    assert stream.queue.empty()
