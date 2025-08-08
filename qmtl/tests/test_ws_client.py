import asyncio
import json
import logging

import pytest
import websockets

from qmtl.sdk.ws_client import WebSocketClient


@pytest.mark.asyncio
async def test_ws_client_updates_state():
    events = [
        {"event": "queue_created", "queue_id": "n1", "topic": "t1"},
        {"event": "sentinel_weight", "sentinel_id": "s1", "weight": 0.75},
        {
            "event": "queue_update",
            "tags": ["t"],
            "interval": 60,
            "queues": ["q1"],
            "match_mode": "any",
        },
    ]

    async def handler(websocket):
        for e in events:
            await websocket.send(json.dumps(e))
        await asyncio.sleep(0.05)

    server = await websockets.serve(handler, "localhost", 0)
    port = server.sockets[0].getsockname()[1]
    url = f"ws://localhost:{port}"
    try:
        received: list[dict] = []

        async def on_msg(data):
            received.append(data)

        client = WebSocketClient(url, on_message=on_msg)
        await client.start()
        await asyncio.sleep(0.2)
        await client.stop()
        assert client.queue_topics == {"n1": "t1"}
        assert client.sentinel_weights == {"s1": 0.75}
        assert any((d.get("event") or d.get("type")) == "queue_update" for d in received)
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_ws_client_reconnects(monkeypatch):
    """Client reconnects with backoff on connection loss."""

    class DummyWS:
        def __init__(self, messages: list[str]):
            self._messages = messages
            self.close_timeout = 0

        async def recv(self) -> str:
            if self._messages:
                return self._messages.pop(0)
            raise websockets.ConnectionClosed(1000, "")

        async def close(self) -> None:  # pragma: no cover - no behavior
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    connects: list[str] = []

    def fake_connect(url: str):
        connects.append(url)
        if len(connects) == 1:
            return DummyWS([])
        return DummyWS([json.dumps({"event": "queue_update"})])

    monkeypatch.setattr(websockets, "connect", fake_connect)

    received: list[dict] = []

    async def on_msg(data: dict) -> None:
        received.append(data)

    client = WebSocketClient(
        "ws://dummy",
        on_message=on_msg,
        max_retries=1,
        base_delay=0.01,
    )
    await client.start()
    await asyncio.sleep(0.1)
    await client.stop()

    assert len(connects) == 2
    assert any((d.get("event") or d.get("type")) == "queue_update" for d in received)


@pytest.mark.asyncio
async def test_ws_client_stop_closes_session():
    async def handler(websocket):
        await asyncio.sleep(1)

    server = await websockets.serve(handler, "localhost", 0)
    port = server.sockets[0].getsockname()[1]
    url = f"ws://localhost:{port}"
    try:
        client = WebSocketClient(url)
        await client.start()
        await asyncio.sleep(0.1)
        start = asyncio.get_running_loop().time()
        await client.stop()
        assert asyncio.get_running_loop().time() - start < 0.5
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_ws_client_logs_invalid_weight(caplog):
    events = [{"event": "sentinel_weight", "sentinel_id": "s1", "weight": "bad"}]

    async def handler(websocket):
        for e in events:
            await websocket.send(json.dumps(e))
        await asyncio.sleep(0.05)

    server = await websockets.serve(handler, "localhost", 0)
    port = server.sockets[0].getsockname()[1]
    url = f"ws://localhost:{port}"
    try:
        client = WebSocketClient(url)
        with caplog.at_level(logging.WARNING):
            await client.start()
            await asyncio.sleep(0.2)
            await client.stop()
        assert client.sentinel_weights == {}
        assert any("s1" in r.getMessage() and "bad" in r.getMessage() for r in caplog.records)
    finally:
        server.close()
        await server.wait_closed()
