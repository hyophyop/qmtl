import asyncio
import json

import pytest
import websockets

from qmtl.sdk.ws_client import WebSocketClient


@pytest.mark.asyncio
async def test_ws_client_updates_state():
    events = [
        {"event": "queue_created", "queue_id": "n1", "topic": "t1"},
        {"event": "sentinel_weight", "sentinel_id": "s1", "weight": 0.75},
    ]

    async def handler(websocket):
        for e in events:
            await websocket.send(json.dumps(e))
        await asyncio.sleep(0.05)

    server = await websockets.serve(handler, "localhost", 0)
    port = server.sockets[0].getsockname()[1]
    url = f"ws://localhost:{port}"
    try:
        client = WebSocketClient(url)
        await client.start()
        await asyncio.sleep(0.2)
        await client.stop()
        assert client.queue_topics == {"n1": "t1"}
        assert client.sentinel_weights == {"s1": 0.75}
    finally:
        server.close()
        await server.wait_closed()
