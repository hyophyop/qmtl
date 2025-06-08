import asyncio
import json
import logging
import time

import pytest
import websockets

from qmtl.gateway.ws import WebSocketHub


@pytest.mark.asyncio
async def test_hub_broadcasts_progress_and_queue_map():
    hub = WebSocketHub()
    port = await hub.start()
    url = f"ws://localhost:{port}"
    received: list[dict] = []

    async def client():
        async with websockets.connect(url) as ws:
            while len(received) < 2:
                msg = await ws.recv()
                received.append(json.loads(msg))

    task = asyncio.create_task(client())
    await asyncio.sleep(0.05)
    await hub.send_progress("s1", "queued")
    await hub.send_queue_map("s1", {"n1": "t1"})
    await asyncio.sleep(0.1)
    await hub.stop()
    await task

    types = {evt["type"] for evt in received}
    assert "progress" in types
    assert "queue_map" in types
    for evt in received:
        assert evt["specversion"] == "1.0"
        assert "id" in evt and evt["id"]
        assert "source" in evt
        assert "time" in evt
        assert evt["datacontenttype"] == "application/json"
        assert isinstance(evt.get("data"), dict)


@pytest.mark.asyncio
async def test_hub_line_rate_500_msgs_per_sec():
    hub = WebSocketHub()
    port = await hub.start()
    url = f"ws://localhost:{port}"
    total = 1000
    received = 0

    async def client():
        nonlocal received
        async with websockets.connect(url) as ws:
            while received < total:
                await ws.recv()
                received += 1

    task = asyncio.create_task(client())
    await asyncio.sleep(0.05)
    start = time.perf_counter()
    for i in range(total):
        await hub.send_progress("s", str(i))
    await task
    duration = time.perf_counter() - start
    await hub.stop()

    assert received == total
    assert received / duration >= 500


@pytest.mark.asyncio
async def test_hub_logs_send_errors(caplog):
    hub = WebSocketHub()
    await hub.start()

    class DummyWS:
        remote_address = ("dummy", 1234)

        async def send(self, msg):
            raise RuntimeError("boom")

    async with hub._lock:
        hub._clients.add(DummyWS())

    with caplog.at_level(logging.WARNING):
        await hub.send_progress("s1", "queued")
        await asyncio.sleep(0.1)

    await hub.stop()

    assert any(
        "Failed to send message to client" in record.message for record in caplog.records
    )
