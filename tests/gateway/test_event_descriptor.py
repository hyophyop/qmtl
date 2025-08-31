import httpx
import time
import pytest

from qmtl.gateway.api import create_app, Database
from qmtl.gateway.event_descriptor import (
    EventDescriptorConfig,
    validate_event_token,
    get_token_header,
    sign_event_token,
    jwks,
)


class FakeDB(Database):
    async def insert_strategy(self, strategy_id: str, meta: dict | None) -> None:
        return None

    async def set_status(self, strategy_id: str, status: str) -> None:
        return None

    async def get_status(self, strategy_id: str) -> str | None:
        return None

    async def append_event(self, strategy_id: str, event: str) -> None:
        return None


@pytest.mark.asyncio
async def test_event_descriptor_scope_and_expiry(fake_redis):
    cfg = EventDescriptorConfig(
        keys={"kid1": "s3cr3t"},
        active_kid="kid1",
        ttl=60,
        stream_url="wss://gateway/ws/evt",
        fallback_url="wss://gateway/ws/fallback",
    )
    app = create_app(redis_client=fake_redis, database=FakeDB(), event_config=cfg)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "world_id": "w1",
            "strategy_id": "s1",
            "topics": ["activation"],
        }
        resp = await client.post("/events/subscribe", json=payload)
    await transport.aclose()
    assert resp.status_code == 200
    data = resp.json()
    assert data["stream_url"] == cfg.stream_url
    assert data["topics"] == ["activation"]
    token = data["token"]
    claims = validate_event_token(token, cfg)
    assert claims["world_id"] == "w1"
    assert claims["strategy_id"] == "s1"
    assert claims["topics"] == ["activation"]
    assert "kid" not in claims
    header = get_token_header(token)
    assert header["kid"] == cfg.active_kid
    now = int(time.time())
    assert 50 <= claims["exp"] - now <= 60


@pytest.mark.asyncio
async def test_event_descriptor_secret_from_env(fake_redis, monkeypatch):
    monkeypatch.setenv("QMTL_EVENT_SECRET", "envsecret")
    app = create_app(redis_client=fake_redis, database=FakeDB())
    cfg: EventDescriptorConfig = app.state.event_config
    assert cfg.keys[cfg.active_kid] == "envsecret"


@pytest.mark.asyncio
async def test_event_descriptor_rotation_and_jwks():
    cfg = EventDescriptorConfig(
        keys={"old": "s1", "new": "s2"},
        active_kid="old",
        ttl=60,
        stream_url="wss://gateway/ws/evt",
        fallback_url="wss://gateway/ws/fallback",
    )
    claims = {"aud": "controlbus", "sub": "s1"}
    tok_old = sign_event_token(claims, cfg)
    cfg.active_kid = "new"
    tok_new = sign_event_token(claims, cfg)
    assert validate_event_token(tok_old, cfg)["sub"] == "s1"
    assert validate_event_token(tok_new, cfg)["sub"] == "s1"
    keyset = jwks(cfg)
    assert {k["kid"] for k in keyset["keys"]} == {"old", "new"}
