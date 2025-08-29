import pytest
import httpx
from fastapi import FastAPI, Response, Request

from qmtl.gateway.api import create_app, Database
from qmtl.gateway.world_client import WorldClient
from qmtl.gateway import metrics


class FakeDB(Database):
    async def insert_strategy(self, strategy_id: str, meta):
        pass

    async def set_status(self, strategy_id: str, status: str):
        pass

    async def get_status(self, strategy_id: str):
        return "queued"

    async def append_event(self, strategy_id: str, event: str):
        pass


@pytest.mark.asyncio
async def test_decide_ttl_cache(fake_redis):
    metrics.reset_metrics()
    ws_app = FastAPI()
    calls = {"decide": 0}

    @ws_app.get("/worlds/{world_id}/decide")
    async def decide(world_id: str):
        calls["decide"] += 1
        return {"decision": "hold", "ttl": 60}

    ws_client = WorldClient(
        "http://ws",
        http_client=httpx.AsyncClient(transport=httpx.ASGITransport(app=ws_app), base_url="http://ws"),
    )
    app = create_app(redis_client=fake_redis, database=FakeDB(), world_client=ws_client)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://gw") as client:
        headers = {"Authorization": "Bearer token"}
        r1 = await client.get("/worlds/foo/decide", headers=headers)
        assert r1.status_code == 200
        r2 = await client.get("/worlds/foo/decide", headers=headers)
        assert r2.status_code == 200
        r3 = await client.get("/worlds/foo/decide")
        assert r3.status_code == 200
    assert calls["decide"] == 2
    assert metrics.worldservice_cache_hits_total.labels(endpoint="decide")._value.get() == 1


@pytest.mark.asyncio
async def test_activation_etag_cache(fake_redis):
    metrics.reset_metrics()
    ws_app = FastAPI()
    calls = {"activation": 0}

    @ws_app.get("/worlds/{world_id}/activation")
    async def activation(world_id: str, request: Request, response: Response):
        calls["activation"] += 1
        etag = '"v1"'
        if request.headers.get("if-none-match") == etag:
            response.status_code = 304
            return Response(status_code=304)
        response.headers["ETag"] = etag
        return {"active": True}

    ws_client = WorldClient(
        "http://ws",
        http_client=httpx.AsyncClient(transport=httpx.ASGITransport(app=ws_app), base_url="http://ws"),
    )
    app = create_app(redis_client=fake_redis, database=FakeDB(), world_client=ws_client)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://gw") as client:
        r1 = await client.get("/worlds/foo/activation")
        assert r1.status_code == 200 and r1.json()["active"] is True
        etag = r1.headers.get("etag")
        r2 = await client.get("/worlds/foo/activation", headers={"If-None-Match": etag})
        assert r2.status_code == 304
    assert calls["activation"] == 1
    assert metrics.worldservice_cache_hits_total.labels(endpoint="activation")._value.get() == 1


@pytest.mark.asyncio
async def test_apply_live_guard(fake_redis):
    ws_app = FastAPI()
    calls = {"apply": 0}

    @ws_app.post("/worlds/{world_id}/apply")
    async def apply(world_id: str):
        calls["apply"] += 1
        return {"status": "ok"}

    ws_client = WorldClient(
        "http://ws",
        http_client=httpx.AsyncClient(transport=httpx.ASGITransport(app=ws_app), base_url="http://ws"),
    )
    app = create_app(redis_client=fake_redis, database=FakeDB(), world_client=ws_client)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://gw") as client:
        r1 = await client.post("/worlds/foo/apply", json={})
        assert r1.status_code == 403
        r2 = await client.post("/worlds/foo/apply", json={}, headers={"X-Allow-Live": "true"})
        assert r2.status_code == 200
    assert calls["apply"] == 1
