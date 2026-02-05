import json
import hashlib
import hmac
import time

import httpx
import pytest

from qmtl.services.gateway.api import create_app, Database
from qmtl.services.gateway.event_descriptor import EventDescriptorConfig, sign_event_token


class FakeDB(Database):
    def __init__(self):
        self.records = {}
        self.events = []

    async def insert_strategy(self, strategy_id: str, meta: dict | None) -> None:
        self.records[strategy_id] = {"meta": meta, "status": "queued"}

    async def set_status(self, strategy_id: str, status: str) -> None:
        if strategy_id in self.records:
            self.records[strategy_id]["status"] = status

    async def get_status(self, strategy_id: str) -> str | None:
        rec = self.records.get(strategy_id)
        return rec.get("status") if rec else None

    async def append_event(self, strategy_id: str, event: str) -> None:  # pragma: no cover - not used
        self.events.append((strategy_id, event))


class FakeProducer:
    def __init__(self):
        self.messages = []

    async def send_and_wait(self, topic, value, key=None, headers=None):
        self.messages.append((topic, value, key, headers))


def _event_config() -> EventDescriptorConfig:
    return EventDescriptorConfig(
        keys={"k1": "secret"},
        active_kid="k1",
        ttl=60,
        stream_url="",
        fallback_url="",
    )


def _sign_fills_token(
    cfg: EventDescriptorConfig,
    *,
    world_id: str = "w1",
    strategy_id: str = "s1",
) -> str:
    now = int(time.time())
    claims = {
        "aud": "fills",
        "sub": strategy_id or "unknown",
        "world_id": world_id,
        "strategy_id": strategy_id,
        "jti": "1",
        "iat": now,
        "exp": now + 60,
    }
    return sign_event_token(claims, cfg)


def _ce_payload(**overrides):
    payload = {
        "specversion": "1.0",
        "id": "evt-1",
        "type": "trade.fill",
        "source": "test://fills",
        "time": "2025-01-01T00:00:00Z",
        "data": {
            "order_id": "exch-7890",
            "symbol": "BTC/USDT",
            "side": "BUY",
            "quantity": 1.0,
            "price": 100.0,
            "extra": "drop-me",
        },
    }
    payload.update(overrides)
    return payload


def _signed_hmac_payload(payload: dict, secret: str) -> tuple[bytes, str]:
    raw = json.dumps(payload, separators=(",", ":")).encode()
    signature = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return raw, signature


@pytest.mark.asyncio
async def test_fills_webhook_produces_kafka(fake_redis):
    cfg = _event_config()
    producer = FakeProducer()
    app = create_app(
        redis_client=fake_redis,
        database=FakeDB(),
        enable_background=False,
        event_config=cfg,
        fill_producer=producer,
    )
    token = _sign_fills_token(cfg)
    payload = _ce_payload()
    async with httpx.ASGITransport(app=app) as transport:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/fills", json=payload, headers={"Authorization": f"Bearer {token}"})
            assert resp.status_code == 202
    assert producer.messages
    topic, value, key, headers = producer.messages[0]
    assert topic == "trade.fills"
    assert key == b"w1|s1|BTC/USDT|exch-7890"
    data = json.loads(value)
    assert data["order_id"] == "exch-7890"
    assert "extra" not in data
    assert any(h[0] == "rfp" for h in headers or [])


@pytest.mark.asyncio
async def test_fills_webhook_hmac_fallback_success(fake_redis, monkeypatch):
    cfg = _event_config()
    producer = FakeProducer()
    app = create_app(
        redis_client=fake_redis,
        database=FakeDB(),
        enable_background=False,
        event_config=cfg,
        fill_producer=producer,
    )
    monkeypatch.setenv("QMTL_FILL_SECRET", "fallback-secret")
    payload = _ce_payload(world_id="w-fallback", strategy_id="s-fallback")
    raw, signature = _signed_hmac_payload(payload, "fallback-secret")
    async with httpx.ASGITransport(app=app) as transport:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/fills",
                content=raw,
                headers={
                    "Content-Type": "application/json",
                    "X-Signature": signature,
                },
            )
    assert resp.status_code == 202
    assert producer.messages
    _, _, key, _ = producer.messages[0]
    assert key == b"w-fallback|s-fallback|BTC/USDT|exch-7890"


@pytest.mark.asyncio
async def test_fills_webhook_missing_auth_returns_e_auth(fake_redis, monkeypatch):
    cfg = _event_config()
    app = create_app(
        redis_client=fake_redis,
        database=FakeDB(),
        enable_background=False,
        event_config=cfg,
        fill_producer=FakeProducer(),
    )
    monkeypatch.delenv("QMTL_FILL_SECRET", raising=False)
    async with httpx.ASGITransport(app=app) as transport:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/fills", json=_ce_payload())
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "E_AUTH"


@pytest.mark.asyncio
async def test_fills_webhook_bad_signature_returns_e_auth(fake_redis, monkeypatch):
    cfg = _event_config()
    app = create_app(
        redis_client=fake_redis,
        database=FakeDB(),
        enable_background=False,
        event_config=cfg,
        fill_producer=FakeProducer(),
    )
    monkeypatch.setenv("QMTL_FILL_SECRET", "fallback-secret")
    payload = _ce_payload(world_id="w1", strategy_id="s1")
    raw, _ = _signed_hmac_payload(payload, "fallback-secret")
    async with httpx.ASGITransport(app=app) as transport:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/fills",
                content=raw,
                headers={
                    "Content-Type": "application/json",
                    "X-Signature": "bad-signature",
                },
            )
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "E_AUTH"


@pytest.mark.asyncio
async def test_fills_webhook_missing_cloudevents_envelope_returns_e_ce_required(fake_redis):
    cfg = _event_config()
    app = create_app(
        redis_client=fake_redis,
        database=FakeDB(),
        enable_background=False,
        event_config=cfg,
        fill_producer=FakeProducer(),
    )
    token = _sign_fills_token(cfg)
    payload = {"data": _ce_payload()["data"]}
    async with httpx.ASGITransport(app=app) as transport:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/fills",
                json=payload,
                headers={"Authorization": f"Bearer {token}"},
            )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "E_CE_REQUIRED"


@pytest.mark.asyncio
async def test_fills_webhook_missing_ids_returns_e_missing_ids(fake_redis):
    cfg = _event_config()
    app = create_app(
        redis_client=fake_redis,
        database=FakeDB(),
        enable_background=False,
        event_config=cfg,
        fill_producer=FakeProducer(),
    )
    token = _sign_fills_token(cfg, world_id="", strategy_id="")
    async with httpx.ASGITransport(app=app) as transport:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/fills",
                json=_ce_payload(),
                headers={"Authorization": f"Bearer {token}"},
            )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "E_MISSING_IDS"


@pytest.mark.asyncio
async def test_fills_webhook_schema_invalid_returns_e_schema_invalid(fake_redis):
    cfg = _event_config()
    app = create_app(
        redis_client=fake_redis,
        database=FakeDB(),
        enable_background=False,
        event_config=cfg,
        fill_producer=FakeProducer(),
    )
    token = _sign_fills_token(cfg)
    payload = _ce_payload(
        data={
            "order_id": "exch-7890",
            "symbol": "BTC/USDT",
            "side": "BUY",
            "quantity": "1.0",
            "price": 100.0,
        }
    )
    async with httpx.ASGITransport(app=app) as transport:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/fills",
                json=payload,
                headers={"Authorization": f"Bearer {token}"},
            )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "E_SCHEMA_INVALID"
    assert resp.json()["detail"]["errors"]


@pytest.mark.asyncio
async def test_fills_webhook_forwards_cloudevents_headers(fake_redis):
    cfg = _event_config()
    producer = FakeProducer()
    app = create_app(
        redis_client=fake_redis,
        database=FakeDB(),
        enable_background=False,
        event_config=cfg,
        fill_producer=producer,
    )
    token = _sign_fills_token(cfg)
    payload = _ce_payload(
        id="evt-forward",
        type="trade.fill.forwarded",
        source="test://forward",
        time="2025-01-01T01:23:45Z",
    )
    async with httpx.ASGITransport(app=app) as transport:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/fills",
                json=payload,
                headers={"Authorization": f"Bearer {token}"},
            )
    assert resp.status_code == 202
    assert producer.messages
    _, _, _, headers = producer.messages[0]
    header_map = {k: v for k, v in headers or []}
    assert header_map["ce_id"] == b"evt-forward"
    assert header_map["ce_type"] == b"trade.fill.forwarded"
    assert header_map["ce_source"] == b"test://forward"
    assert header_map["ce_time"] == b"2025-01-01T01:23:45Z"
