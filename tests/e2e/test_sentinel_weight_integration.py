import asyncio
import json

import httpx
import pytest
import websockets

from qmtl.dagmanager.http_server import create_app as dag_create_app
from qmtl.gateway.api import create_app as gw_create_app
from qmtl.gateway.ws import WebSocketHub


@pytest.mark.asyncio
@pytest.mark.filterwarnings("ignore::ResourceWarning")
async def test_sentinel_traffic_triggers_ws(monkeypatch):
    hub = WebSocketHub()
    port = await hub.start()
    gw_app = gw_create_app(ws_hub=hub)
    gw_transport = httpx.ASGITransport(gw_app)

    async def post_to_gateway(url: str, json: dict, **_):
        async with httpx.AsyncClient(transport=gw_transport, base_url="http://gw") as client:
            path = url.replace("http://gw", "")
            return await client.post(path, json=json)

    monkeypatch.setattr("qmtl.dagmanager.http_server.post", post_to_gateway)

    dag_app = dag_create_app(gateway_url="http://gw/callbacks/dag-event")
    dag_transport = httpx.ASGITransport(dag_app)

    async with websockets.connect(f"ws://localhost:{port}") as ws:
        async with httpx.AsyncClient(transport=dag_transport, base_url="http://dag") as client:
            resp = await client.post(
                "/callbacks/sentinel-traffic",
                json={"version": "v1", "weight": 0.55},
            )
            assert resp.status_code == 202

        msg = await ws.recv()
        event = json.loads(msg)

    await asyncio.sleep(0)
    await hub.stop()
    await asyncio.sleep(0)

    assert event["type"] == "sentinel_weight"
    assert event["data"] == {"sentinel_id": "v1", "weight": 0.55}
