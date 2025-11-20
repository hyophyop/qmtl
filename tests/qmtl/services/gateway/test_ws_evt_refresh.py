import time
from typing import Any, cast

import pytest
from fastapi import FastAPI, WebSocketDisconnect
from fastapi.testclient import TestClient

from qmtl.services.gateway.event_handlers import create_event_router
from qmtl.services.gateway.event_descriptor import EventDescriptorConfig, sign_event_token
from qmtl.services.gateway.ws import WebSocketHub
from qmtl.services.gateway import metrics as gw_metrics


def _make_token(cfg: EventDescriptorConfig, *, world: str, strat: str, topics=None) -> str:
    now = int(time.time())
    claims = {
        "aud": "controlbus",
        "sub": strat,
        "world_id": world,
        "strategy_id": strat,
        "topics": topics or [],
        "jti": "j1",
        "iat": now,
        "exp": now + 60,
    }
    return sign_event_token(claims, cfg)


def test_refresh_updates_topics_and_filters():
    gw_metrics.reset_metrics()
    hub = WebSocketHub()
    cfg = EventDescriptorConfig(keys={"k": "secret"}, active_kid="k")
    app = FastAPI()
    app.include_router(create_event_router(hub, cfg))

    tok1 = _make_token(cfg, world="w1", strat="s1", topics=[])
    tok2 = _make_token(cfg, world="w2", strat="s2", topics=["policy"])

    with TestClient(app) as client:
        with client.websocket_connect("/ws/evt", headers={"Authorization": f"Bearer {tok1}"}) as ws:
            ws.send_json({"type": "refresh", "token": tok2})
            ack = ws.receive_json()
            assert ack["type"] == "refresh_ack"
            registry = cast(Any, hub)._registry
            topics = next(iter(registry._topics.values()))
            assert topics == {"policy"}
            filt = next(iter(registry._filters.values()))
            assert filt.world_id == "w2"
            assert filt.strategy_id == "s2"


def test_invalid_refresh_closes_connection():
    gw_metrics.reset_metrics()
    hub = WebSocketHub()
    cfg = EventDescriptorConfig(keys={"k": "secret"}, active_kid="k")
    app = FastAPI()
    app.include_router(create_event_router(hub, cfg))

    tok = _make_token(cfg, world="w1", strat="s1", topics=[])

    with TestClient(app) as client:
        with client.websocket_connect("/ws/evt", headers={"Authorization": f"Bearer {tok}"}) as ws:
            ws.send_json({"type": "refresh", "token": "bad"})
            with pytest.raises(WebSocketDisconnect) as exc:
                ws.receive_json()
            assert exc.value.code == 1008
    assert gw_metrics.ws_refresh_failures_total._value.get() == 1
