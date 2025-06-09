import asyncio
import json

import httpx
import pytest
import websockets

from qmtl.dagmanager.http_server import create_app as dag_create_app
from qmtl.gateway.api import create_app as gw_create_app
from qmtl.gateway.ws import WebSocketHub


@pytest.mark.asyncio
async def test_sentinel_traffic_triggers_ws(monkeypatch):
    hub = WebSocketHub()
    port = await hub.start()
    gw_app = gw_create_app(ws_hub=hub)
    gw_transport = httpx.ASGITransport(gw_app)

    async def post_to_gateway(url: str, json: dict, **_):
        async with httpx.AsyncClient(transport=gw_transport, base_url="http://gw") as client:
            path = url.replace("http://gw", "")
            return await client.post(path, json=json)

    monkeypatch.setattr("qmtl.dagmanager.http_server.post_with_backoff", post_to_gateway)

    dag_app = dag_create_app(gateway_url="http://gw/callbacks/dag-event")
    dag_transport = httpx.ASGITransport(dag_app)

    received = []

    async def ws_client():
        async with websockets.connect(f"ws://localhost:{port}") as ws:
            msg = await ws.recv()
            received.append(json.loads(msg))

    client_task = asyncio.create_task(ws_client())
    await asyncio.sleep(0.1)

    async with httpx.AsyncClient(transport=dag_transport, base_url="http://dag") as client:
        resp = await client.post(
            "/callbacks/sentinel-traffic",
            json={"version": "v1", "weight": 0.55},
        )
        assert resp.status_code == 202

    await asyncio.sleep(0.1)
    await hub.stop()
    await client_task

    assert received
    event = received[0]
    assert event["type"] == "sentinel_weight"
    assert event["data"] == {"sentinel_id": "v1", "weight": 0.55}
