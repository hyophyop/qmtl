import pytest
import httpx

from qmtl.gateway.api import create_app, Database
from qmtl.gateway.world_client import WorldServiceClient


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
async def test_decide_ttl_cache(fake_redis):
    call_count = {"n": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/decide"):
            call_count["n"] += 1
            return httpx.Response(200, json={"v": call_count["n"]}, headers={"Cache-Control": "max-age=60"})
        raise AssertionError("unexpected path")

    transport = httpx.MockTransport(handler)
    client = WorldServiceClient("http://world", client=httpx.AsyncClient(transport=transport))
    app = create_app(redis_client=fake_redis, database=FakeDB(), world_client=client)
    asgi = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=asgi, base_url="http://test") as api_client:
        r1 = await api_client.get("/worlds/abc/decide")
        r2 = await api_client.get("/worlds/abc/decide")
    await asgi.aclose()
    await client._client.aclose()
    assert r1.json() == {"v": 1}
    assert r2.json() == {"v": 1}
    assert call_count["n"] == 1


@pytest.mark.asyncio
async def test_activation_etag_cache(fake_redis):
    call_count = {"n": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/activation"):
            if request.headers.get("If-None-Match") == "abc":
                return httpx.Response(304, headers={"ETag": "abc"})
            call_count["n"] += 1
            return httpx.Response(200, json={"a": call_count["n"]}, headers={"ETag": "abc"})
        raise AssertionError("unexpected path")

    transport = httpx.MockTransport(handler)
    client = WorldServiceClient("http://world", client=httpx.AsyncClient(transport=transport))
    app = create_app(redis_client=fake_redis, database=FakeDB(), world_client=client)
    asgi = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=asgi, base_url="http://test") as api_client:
        r1 = await api_client.get("/worlds/abc/activation")
        r2 = await api_client.get("/worlds/abc/activation")
    await asgi.aclose()
    await client._client.aclose()
    assert r1.json() == {"a": 1}
    assert r2.json() == {"a": 1}
    assert call_count["n"] == 1


@pytest.mark.asyncio
async def test_live_guard(fake_redis):
    call_count = {"n": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/apply"):
            call_count["n"] += 1
            return httpx.Response(200, json={"ok": True})
        raise AssertionError("unexpected path")

    transport = httpx.MockTransport(handler)
    client = WorldServiceClient("http://world", client=httpx.AsyncClient(transport=transport))
    app = create_app(redis_client=fake_redis, database=FakeDB(), world_client=client)
    asgi = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=asgi, base_url="http://test") as api_client:
        r1 = await api_client.post("/worlds/abc/apply", json={})
        r2 = await api_client.post("/worlds/abc/apply", json={}, headers={"X-Allow-Live": "true"})
    await asgi.aclose()
    await client._client.aclose()
    assert r1.status_code == 403
    assert r2.status_code == 200
    assert call_count["n"] == 1


@pytest.mark.asyncio
async def test_decide_ttl_envelope_fallback(fake_redis):
    calls = {"n": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/decide"):
            calls["n"] += 1
            # No Cache-Control header; envelope carries ttl
            return httpx.Response(200, json={"v": calls["n"], "ttl": "300s"})
        raise AssertionError("unexpected path")

    transport = httpx.MockTransport(handler)
    client = WorldServiceClient("http://world", client=httpx.AsyncClient(transport=transport))
    app = create_app(redis_client=fake_redis, database=FakeDB(), world_client=client)
    asgi = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=asgi, base_url="http://test") as api_client:
        r1 = await api_client.get("/worlds/abc/decide")
        r2 = await api_client.get("/worlds/abc/decide")
    await asgi.aclose()
    await client._client.aclose()
    assert r1.json() == {"v": 1, "ttl": "300s"}
    assert r2.json() == {"v": 1, "ttl": "300s"}
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_decide_ttl_zero_no_cache(fake_redis):
    calls = {"n": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/decide"):
            calls["n"] += 1
            # No Cache-Control; envelope explicitly disables caching
            return httpx.Response(200, json={"v": calls["n"], "ttl": "0s"})
        raise AssertionError("unexpected path")

    transport = httpx.MockTransport(handler)
    client = WorldServiceClient("http://world", client=httpx.AsyncClient(transport=transport))
    app = create_app(redis_client=fake_redis, database=FakeDB(), world_client=client)
    asgi = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=asgi, base_url="http://test") as api_client:
        r1 = await api_client.get("/worlds/abc/decide")
        r2 = await api_client.get("/worlds/abc/decide")
    await asgi.aclose()
    await client._client.aclose()
    assert r1.json() == {"v": 1, "ttl": "0s"}
    assert r2.json() == {"v": 2, "ttl": "0s"}
    # No cache should have been used
    assert calls["n"] == 2
