import os
os.environ["OTEL_SDK_DISABLED"] = "true"
import pytest
import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from qmtl.gateway.event_handlers import create_event_router, normalize_topics
from qmtl.gateway.event_descriptor import EventDescriptorConfig
from qmtl.gateway.ws import WebSocketHub
from qmtl.gateway.api import create_app


class NoServerHub(WebSocketHub):
    async def start(self) -> int:  # type: ignore[override]
        return 0

    async def stop(self) -> None:  # type: ignore[override]
        async with self._lock:
            self._clients.clear()


def test_normalize_topics_aliases() -> None:
    assert normalize_topics(["queues", "queue", "activation", "unknown"]) == {
        "queue",
        "activation",
    }


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
    async with httpx.ASGITransport(app=app) as transport:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/events/jwks")
            assert resp.status_code == 200
            payload = {"world_id": "w", "strategy_id": "s", "topics": ["queues"]}
            sub = await client.post("/events/subscribe", json=payload)
            assert sub.status_code == 200
            data = sub.json()
            assert data["stream_url"] == "ws://test/ws"
            assert data["topics"] == ["queues"]


def test_ws_fallback_endpoint_connects():
    hub = NoServerHub()
    app = create_app(ws_hub=hub, enable_background=False)
    with TestClient(app) as client:
        resp = client.post(
            "/events/subscribe",
            json={"world_id": "w", "strategy_id": "s", "topics": []},
        )
        assert resp.status_code == 200
        assert resp.json()["fallback_url"] == "wss://gateway/ws"
        with client.websocket_connect("/ws") as ws:
            ws.send_text("ping")
