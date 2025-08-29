import asyncio
import json
import logging
import time

import pytest

from qmtl.gateway.ws import WebSocketHub


class DummyWS:
    def __init__(self):
        self.messages: list[str] = []
        self.remote_address = ("test", 0)

    async def send(self, msg: str) -> None:
        self.messages.append(msg)


@pytest.mark.asyncio
async def test_hub_broadcasts_progress_and_queue_map():
    hub = WebSocketHub()
    await hub.start()
    ws = DummyWS()
    async with hub._lock:
        hub._clients.add(ws)
    await hub.send_progress("s1", "queued")
    await hub.send_queue_map("s1", {"n1": "t1"})
    await asyncio.sleep(0.1)
    await hub.stop()
    assert len(ws.messages) == 2
    types = {json.loads(m)["type"] for m in ws.messages}
    assert "progress" in types
    assert "queue_map" in types


@pytest.mark.asyncio
async def test_hub_line_rate_500_msgs_per_sec():
    hub = WebSocketHub()
    await hub.start()
    ws = DummyWS()
    async with hub._lock:
        hub._clients.add(ws)
    total = 1000
    start = time.perf_counter()
    for i in range(total):
        await hub.send_progress("s", str(i))
    while len(ws.messages) < total:
        await asyncio.sleep(0)
    duration = time.perf_counter() - start
    await hub.stop()
    assert len(ws.messages) == total
    assert len(ws.messages) / duration >= 500


@pytest.mark.asyncio
async def test_hub_logs_send_errors(caplog):
    hub = WebSocketHub()
    await hub.start()

    class BadWS:
        remote_address = ("dummy", 1234)

        async def send(self, msg):
            raise RuntimeError("boom")

    async with hub._lock:
        hub._clients.add(BadWS())

    with caplog.at_level(logging.WARNING):
        await hub.send_progress("s1", "queued")
        await asyncio.sleep(0.1)
    await hub.stop()
    assert any(
        "Failed to send message to client" in record.message for record in caplog.records
    )


@pytest.mark.asyncio
async def test_hub_sends_sentinel_weight():
    hub = WebSocketHub()
    await hub.start()
    ws = DummyWS()
    async with hub._lock:
        hub._clients.add(ws)
    await hub.send_sentinel_weight("s1", 0.5)
    await asyncio.sleep(0.1)
    await hub.stop()
    msg = json.loads(ws.messages[0])
    assert msg["type"] == "sentinel_weight"
    assert msg["data"] == {"sentinel_id": "s1", "weight": 0.5}


@pytest.mark.asyncio
async def test_hub_sends_activation_and_policy():
    hub = WebSocketHub()
    await hub.start()
    ws = DummyWS()
    async with hub._lock:
        hub._clients.add(ws)
    await hub.send_activation_updated({"strategy_id": "s1"})
    await hub.send_policy_updated({"strategy_id": "s1", "limit": 1})
    await asyncio.sleep(0.1)
    await hub.stop()
    types = {json.loads(m)["type"] for m in ws.messages}
    assert "activation_updated" in types
    assert "policy_updated" in types
