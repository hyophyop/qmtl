import json
import time

import httpx
import pytest

from qmtl.gateway.api import create_app, Database
from qmtl.gateway.event_descriptor import EventDescriptorConfig, sign_event_token


class FakeDB(Database):
    async def insert_strategy(self, strategy_id: str, meta: dict | None) -> None:
        return None


@pytest.fixture
def app_and_cfg(fake_redis):
    cfg = EventDescriptorConfig(keys={"k1": "s1"}, active_kid="k1")
    app = create_app(
        redis_client=fake_redis,
        database=FakeDB(),
        event_config=cfg,
        enable_background=False,
    )
    return app, cfg


def _make_token(cfg: EventDescriptorConfig) -> str:
    claims = {
        "aud": "controlbus",
        "exp": int(time.time()) + 60,
        "world_id": "w1",
        "strategy_id": "s1",
    }
    return sign_event_token(claims, cfg)


@pytest.mark.asyncio
async def test_fills_webhook_accepts_bare_and_cloudevent(app_and_cfg, fake_redis):
    app, cfg = app_and_cfg
    token = _make_token(cfg)
    await fake_redis.delete("trade.fills")
    bare = {"world_id": "w1", "strategy_id": "s1"}
    async with httpx.ASGITransport(app=app) as transport:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/fills", headers={"Authorization": f"Bearer {token}"}, json=bare
            )
            assert resp.status_code == 202
            ce = {
                "specversion": "1.0",
                "type": "qmtl.trade.fill",
                "source": "broker/x",
                "id": "1",
                "time": "2025-01-01T00:00:00Z",
                "data": {"world_id": "w1", "strategy_id": "s1"},
            }
            resp = await client.post(
                "/fills", headers={"Authorization": f"Bearer {token}"}, json=ce
            )
            assert resp.status_code == 202
    items = await fake_redis.lrange("trade.fills", 0, -1)
    assert len(items) == 2
    # ensure stored data is JSON
    for raw in items:
        json.loads(raw)


@pytest.mark.asyncio
async def test_fills_replay_publishes_event(app_and_cfg, fake_redis):
    app, cfg = app_and_cfg
    token = _make_token(cfg)
    await fake_redis.delete("trade.fills")
    payload = {"from_ts": 1, "to_ts": 2, "world_id": "w1", "strategy_id": "s1"}
    async with httpx.ASGITransport(app=app) as transport:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/fills/replay", headers={"Authorization": f"Bearer {token}"}, json=payload
            )
            assert resp.status_code == 202
    items = await fake_redis.lrange("trade.fills", 0, -1)
    assert len(items) == 1
    event = json.loads(items[0])
    assert event["data"]["from_ts"] == 1
