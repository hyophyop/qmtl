import pytest
import httpx
from fastapi import FastAPI

from qmtl.gateway.event_handlers import create_event_router
from qmtl.gateway.event_descriptor import EventDescriptorConfig
from qmtl.gateway.ws import WebSocketHub


@pytest.mark.asyncio
async def test_event_subscription_endpoints():
    hub = WebSocketHub()
    cfg = EventDescriptorConfig(
        keys={"k": "secret"},
        active_kid="k",
        ttl=60,
        stream_url="ws://test/ws",
        fallback_url=None,
    )
    app = FastAPI()
    app.include_router(create_event_router(hub, cfg))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/events/jwks")
        assert resp.status_code == 200
        payload = {"world_id": "w", "strategy_id": "s", "topics": ["queues"]}
        sub = await client.post("/events/subscribe", json=payload)
        assert sub.status_code == 200
        data = sub.json()
        assert data["stream_url"] == "ws://test/ws"
        assert data["topics"] == ["queues"]
    await transport.aclose()
