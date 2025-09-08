import json
import time

import httpx
import pytest

from qmtl.gateway.api import create_app, Database
from qmtl.gateway.event_descriptor import EventDescriptorConfig, sign_event_token


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


@pytest.mark.asyncio
async def test_fills_webhook_produces_kafka(fake_redis):
    cfg = EventDescriptorConfig(keys={"k1": "secret"}, active_kid="k1", ttl=60, stream_url="", fallback_url="")
    producer = FakeProducer()
    app = create_app(
        redis_client=fake_redis,
        database=FakeDB(),
        enable_background=False,
        event_config=cfg,
        fill_producer=producer,
    )
    now = int(time.time())
    claims = {
        "aud": "fills",
        "sub": "s1",
        "world_id": "w1",
        "strategy_id": "s1",
        "jti": "1",
        "iat": now,
        "exp": now + 60,
    }
    token = sign_event_token(claims, cfg)
    payload = {
        "order_id": "exch-7890",
        "symbol": "BTC/USDT",
        "side": "BUY",
        "quantity": 1.0,
        "price": 100.0,
        "extra": "drop-me",
    }
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
