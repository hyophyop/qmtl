import asyncio
import json
import logging

import pytest
import websockets

from qmtl.sdk.ws_client import WebSocketClient
from qmtl.common.cloudevents import EVENT_SCHEMA_VERSION


@pytest.mark.asyncio
async def test_ws_client_updates_state():
    events = [
        {
            "event": "queue_created",
            "queue_id": "n1",
            "topic": "t1",
            "version": EVENT_SCHEMA_VERSION,
        },
        {
            "event": "sentinel_weight",
            "sentinel_id": "s1",
            "weight": 0.75,
            "version": EVENT_SCHEMA_VERSION,
        },
        {
            "event": "queue_update",
            "tags": ["t"],
            "interval": 60,
            "queues": [{"queue": "q1", "global": False}],
            "match_mode": "any",
            "version": EVENT_SCHEMA_VERSION,
        },
    ]

    async def handler(websocket):
        for e in events:
            await websocket.send(json.dumps(e))
        await websocket.wait_closed()

    server = await websockets.serve(handler, "localhost", 0)
    port = server.sockets[0].getsockname()[1]
    url = f"ws://localhost:{port}"
    try:
        received: list[dict] = []

        done = asyncio.Event()

        async def on_msg(data):
            received.append(data)
            if (data.get("event") or data.get("type")) == "queue_update":
                done.set()

        client = WebSocketClient(url, on_message=on_msg)
        await client.start()
        await asyncio.wait_for(done.wait(), timeout=1)
        await client.stop()
        assert client.queue_topics == {"n1": "t1"}
        assert client.sentinel_weights == {"s1": 0.75}
        assert any((d.get("event") or d.get("type")) == "queue_update" for d in received)
        assert all(
            d.get("version") == EVENT_SCHEMA_VERSION
            for d in received
            if (d.get("event") or d.get("type")) in {"queue_created", "sentinel_weight", "queue_update"}
        )
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

        async def ping(self) -> None:  # pragma: no cover - no behavior
            return None

        async def close(self) -> None:  # pragma: no cover - no behavior
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    connects: list[str] = []

    def fake_connect(url: str, extra_headers=None):
        connects.append(url)
        if len(connects) == 1:
            return DummyWS([])
        if len(connects) == 2:
            return DummyWS([])
        return DummyWS([json.dumps({"event": "queue_update", "version": EVENT_SCHEMA_VERSION})])

    monkeypatch.setattr(websockets, "connect", fake_connect)

    received: list[dict] = []

    done = asyncio.Event()

    async def on_msg(data: dict) -> None:
        received.append(data)
        done.set()

    client = WebSocketClient(
        "ws://dummy",
        on_message=on_msg,
        max_retries=1,
        base_delay=0.01,
    )
    await client.start()
    await asyncio.wait_for(done.wait(), timeout=1)
    await client.stop()

    assert len(connects) >= 3
    assert any((d.get("event") or d.get("type")) == "queue_update" for d in received)


@pytest.mark.asyncio
async def test_ws_client_stop_closes_session():
    connected = asyncio.Event()

    async def handler(websocket):
        connected.set()
        await websocket.wait_closed()

    server = await websockets.serve(handler, "localhost", 0)
    port = server.sockets[0].getsockname()[1]
    url = f"ws://localhost:{port}"
    try:
        client = WebSocketClient(url)
        await client.start()
        await asyncio.wait_for(connected.wait(), timeout=1)
        start = asyncio.get_running_loop().time()
        await client.stop()
        assert asyncio.get_running_loop().time() - start < 0.5
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_ws_client_logs_invalid_weight(caplog):
    events = [
        {
            "event": "sentinel_weight",
            "sentinel_id": "s1",
            "weight": "bad",
            "version": EVENT_SCHEMA_VERSION,
        }
    ]

    async def handler(websocket):
        for e in events:
            await websocket.send(json.dumps(e))
        await websocket.wait_closed()

    server = await websockets.serve(handler, "localhost", 0)
    port = server.sockets[0].getsockname()[1]
    url = f"ws://localhost:{port}"
    try:
        done = asyncio.Event()

        async def on_msg(data):
            done.set()

        client = WebSocketClient(url, on_message=on_msg)
        with caplog.at_level(logging.WARNING):
            await client.start()
            await asyncio.wait_for(done.wait(), timeout=1)
            await client.stop()
        assert client.sentinel_weights == {}
        assert any("s1" in r.getMessage() and "bad" in r.getMessage() for r in caplog.records)
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_ws_client_sends_token(monkeypatch):
    headers: dict | None = None

    class DummyWS:
        close_timeout = 0

        async def recv(self) -> str:
            raise websockets.ConnectionClosed(1000, "")

        async def ping(self) -> None:  # pragma: no cover - no behavior
            return None

        async def close(self) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    connected = asyncio.Event()

    def fake_connect(url: str, extra_headers=None):
        nonlocal headers
        headers = extra_headers
        connected.set()
        return DummyWS()

    monkeypatch.setattr(websockets, "connect", fake_connect)

    client = WebSocketClient("ws://dummy", token="abc")
    await client.start()
    await asyncio.wait_for(connected.wait(), timeout=1)
    await client.stop()

    assert headers == {"Authorization": "Bearer abc"}
