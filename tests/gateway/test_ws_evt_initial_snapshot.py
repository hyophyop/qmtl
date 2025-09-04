import time
from fastapi import FastAPI
from fastapi.testclient import TestClient

from qmtl.gateway.event_handlers import create_event_router
from qmtl.gateway.event_descriptor import EventDescriptorConfig, sign_event_token
from qmtl.gateway.ws import WebSocketHub


class StubWorldClient:
    async def get_activation(self, world_id, headers=None):
        return (
            {
                "world_id": world_id,
                "strategy_id": "s1",
                "side": "long",
                "active": True,
                "weight": 1.0,
                "etag": "e1",
                "run_id": "r1",
                "ts": "2025-01-01T00:00:00Z",
                "state_hash": "h-act",
            },
            False,
        )

    async def get_state_hash(self, world_id, topic, headers=None):
        return {"state_hash": f"{topic}-hash"}


class StubDagManager:
    async def get_queues_by_tag(
        self, tags, interval, match_mode="any", world_id=None
    ):
        return ["q1", "q2"]


def _make_token(cfg: EventDescriptorConfig) -> str:
    now = int(time.time())
    claims = {
        "aud": "controlbus",
        "sub": "s1",
        "world_id": "w1",
        "strategy_id": "s1",
        "topics": ["queue", "activation", "policy"],
        "jti": "j1",
        "iat": now,
        "exp": now + 60,
    }
    return sign_event_token(claims, cfg)


def test_initial_snapshots_sent_on_connect():
    hub = WebSocketHub()
    cfg = EventDescriptorConfig(keys={"k": "secret"}, active_kid="k")
    app = FastAPI()
    app.include_router(
        create_event_router(hub, cfg, world_client=StubWorldClient(), dagmanager=StubDagManager())
    )

    token = _make_token(cfg)
    with TestClient(app) as client:
        with client.websocket_connect(
            "/ws/evt?tags=t1,t2&interval=60&match_mode=any",
            headers={"Authorization": f"Bearer {token}"},
        ) as ws:
            events = [ws.receive_json(), ws.receive_json(), ws.receive_json()]
    types = {e["type"] for e in events}
    assert types == {"queue_update", "activation_updated", "policy_state_hash"}
