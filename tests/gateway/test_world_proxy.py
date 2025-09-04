import pytest
import httpx
import base64
import json

from qmtl.common import AsyncCircuitBreaker
from qmtl.gateway.api import create_app, Database
from qmtl.gateway.world_client import WorldServiceClient, Budget
from qmtl.gateway import metrics


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
    metrics.reset_metrics()
    call_count = {"n": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/decide"):
            call_count["n"] += 1
            return httpx.Response(200, json={"v": call_count["n"]}, headers={"Cache-Control": "max-age=60"})
        raise AssertionError("unexpected path")

    transport = httpx.MockTransport(handler)
    client = WorldServiceClient("http://world", client=httpx.AsyncClient(transport=transport))
    app = create_app(
        redis_client=fake_redis,
        database=FakeDB(),
        world_client=client,
        enable_background=False,
    )
    asgi = httpx.ASGITransport(app=app, lifespan="on")
    async with httpx.AsyncClient(transport=asgi, base_url="http://test") as api_client:
        r1 = await api_client.get("/worlds/abc/decide")
        r2 = await api_client.get("/worlds/abc/decide")
    await asgi.aclose()
    await client._client.aclose()
    assert r1.json() == {"v": 1}
    assert r2.json() == {"v": 1}
    assert call_count["n"] == 1
    assert metrics.worlds_cache_hit_ratio._value.get() == pytest.approx(0.5)


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
    app = create_app(
        redis_client=fake_redis,
        database=FakeDB(),
        world_client=client,
        enable_background=False,
    )
    asgi = httpx.ASGITransport(app=app, lifespan="on")
    async with httpx.AsyncClient(transport=asgi, base_url="http://test") as api_client:
        r1 = await api_client.get("/worlds/abc/activation")
        r2 = await api_client.get("/worlds/abc/activation")
    await asgi.aclose()
    await client._client.aclose()
    assert r1.json() == {"a": 1}
    assert r2.json() == {"a": 1}
    assert call_count["n"] == 1


@pytest.mark.asyncio
async def test_decide_stale_on_backend_error(fake_redis):
    metrics.reset_metrics()
    calls = {"n": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/decide"):
            calls["n"] += 1
            if calls["n"] == 1:
                return httpx.Response(200, json={"v": 1}, headers={"Cache-Control": "max-age=60"})
            return httpx.Response(500)
        raise AssertionError("unexpected path")

    transport = httpx.MockTransport(handler)
    client = WorldServiceClient("http://world", client=httpx.AsyncClient(transport=transport))
    app = create_app(
        redis_client=fake_redis,
        database=FakeDB(),
        world_client=client,
        enable_background=False,
    )
    asgi = httpx.ASGITransport(app=app, lifespan="on")
    async with httpx.AsyncClient(transport=asgi, base_url="http://test") as api_client:
        r1 = await api_client.get("/worlds/abc/decide")
        client._decision_cache["abc"].expires_at = 0
        r2 = await api_client.get("/worlds/abc/decide")
    await asgi.aclose()
    await client._client.aclose()
    assert r1.json() == {"v": 1}
    assert r2.json() == {"v": 1}
    assert r2.headers["X-Stale"] == "true"
    assert r2.headers["Warning"] == "110 - Response is stale"
    assert metrics.worlds_stale_responses_total._value.get() == 1


@pytest.mark.asyncio
async def test_decide_backend_error_no_cache(fake_redis):
    metrics.reset_metrics()

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/decide"):
            return httpx.Response(500)
        raise AssertionError("unexpected path")

    transport = httpx.MockTransport(handler)
    client = WorldServiceClient("http://world", client=httpx.AsyncClient(transport=transport))
    app = create_app(
        redis_client=fake_redis,
        database=FakeDB(),
        world_client=client,
        enable_background=False,
    )
    asgi = httpx.ASGITransport(app=app, lifespan="on")
    async with httpx.AsyncClient(transport=asgi, base_url="http://test") as api_client:
        with pytest.raises(httpx.HTTPStatusError):
            await api_client.get("/worlds/abc/decide")
    await asgi.aclose()
    await client._client.aclose()
    assert metrics.worlds_stale_responses_total._value.get() == 0


@pytest.mark.asyncio
async def test_activation_stale_on_backend_error(fake_redis):
    metrics.reset_metrics()
    calls = {"n": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/activation"):
            calls["n"] += 1
            if calls["n"] == 1:
                return httpx.Response(200, json={"a": 1}, headers={"ETag": "abc"})
            return httpx.Response(500)
        raise AssertionError("unexpected path")

    transport = httpx.MockTransport(handler)
    client = WorldServiceClient("http://world", client=httpx.AsyncClient(transport=transport))
    app = create_app(
        redis_client=fake_redis,
        database=FakeDB(),
        world_client=client,
        enable_background=False,
    )
    asgi = httpx.ASGITransport(app=app, lifespan="on")
    async with httpx.AsyncClient(transport=asgi, base_url="http://test") as api_client:
        r1 = await api_client.get("/worlds/abc/activation")
        r2 = await api_client.get("/worlds/abc/activation")
    await asgi.aclose()
    await client._client.aclose()
    assert r1.json() == {"a": 1}
    assert r2.json() == {"a": 1}
    assert r2.headers["X-Stale"] == "true"
    assert r2.headers["Warning"] == "110 - Response is stale"
    assert metrics.worlds_stale_responses_total._value.get() == 1


@pytest.mark.asyncio
async def test_activation_backend_error_no_cache(fake_redis):
    metrics.reset_metrics()

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/activation"):
            return httpx.Response(500)
        raise AssertionError("unexpected path")

    transport = httpx.MockTransport(handler)
    client = WorldServiceClient("http://world", client=httpx.AsyncClient(transport=transport))
    app = create_app(
        redis_client=fake_redis,
        database=FakeDB(),
        world_client=client,
        enable_background=False,
    )
    asgi = httpx.ASGITransport(app=app, lifespan="on")
    async with httpx.AsyncClient(transport=asgi, base_url="http://test") as api_client:
        with pytest.raises(httpx.HTTPStatusError):
            await api_client.get("/worlds/abc/activation")
    await asgi.aclose()
    await client._client.aclose()
    assert metrics.worlds_stale_responses_total._value.get() == 0


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
    app = create_app(
        redis_client=fake_redis,
        database=FakeDB(),
        world_client=client,
        enable_background=False,
    )
    asgi = httpx.ASGITransport(app=app, lifespan="on")
    async with httpx.AsyncClient(transport=asgi, base_url="http://test") as api_client:
        r1 = await api_client.post("/worlds/abc/apply", json={})
        r2 = await api_client.post("/worlds/abc/apply", json={}, headers={"X-Allow-Live": "true"})
    await asgi.aclose()
    await client._client.aclose()
    assert r1.status_code == 403
    assert r2.status_code == 200
    assert call_count["n"] == 1


@pytest.mark.asyncio
async def test_live_guard_disabled(fake_redis):
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/apply"):
            return httpx.Response(200, json={"ok": True})
        raise AssertionError("unexpected path")

    transport = httpx.MockTransport(handler)
    client = WorldServiceClient("http://world", client=httpx.AsyncClient(transport=transport))
    app = create_app(
        redis_client=fake_redis,
        database=FakeDB(),
        world_client=client,
        enforce_live_guard=False,
        enable_background=False,
    )
    asgi = httpx.ASGITransport(app=app, lifespan="on")
    async with httpx.AsyncClient(transport=asgi, base_url="http://test") as api_client:
        r = await api_client.post("/worlds/abc/apply", json={})
    await asgi.aclose()
    await client._client.aclose()
    assert r.status_code == 200


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
    app = create_app(redis_client=fake_redis, database=FakeDB(), world_client=client, enable_background=False)
    asgi = httpx.ASGITransport(app=app, lifespan="on")
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
    app = create_app(redis_client=fake_redis, database=FakeDB(), world_client=client, enable_background=False)
    asgi = httpx.ASGITransport(app=app, lifespan="on")
    async with httpx.AsyncClient(transport=asgi, base_url="http://test") as api_client:
        r1 = await api_client.get("/worlds/abc/decide")
        r2 = await api_client.get("/worlds/abc/decide")
    await asgi.aclose()
    await client._client.aclose()
    assert r1.json() == {"v": 1, "ttl": "0s"}
    assert r2.json() == {"v": 2, "ttl": "0s"}
    # No cache should have been used
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_state_hash_probe_divergence(fake_redis):
    hashes = ["h1", "h1", "h2"]
    calls = {"hash": 0, "snap": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/activation/state_hash"):
            idx = calls["hash"]
            calls["hash"] += 1
            return httpx.Response(200, json={"state_hash": hashes[idx]})
        if request.url.path.endswith("/activation"):
            calls["snap"] += 1
            return httpx.Response(200, json={"a": calls["snap"]})
        raise AssertionError("unexpected path")

    transport = httpx.MockTransport(handler)
    client = WorldServiceClient("http://world", client=httpx.AsyncClient(transport=transport))
    app = create_app(
        redis_client=fake_redis,
        database=FakeDB(),
        world_client=client,
        enable_background=False,
    )
    asgi = httpx.ASGITransport(app=app, lifespan="on")
    async with httpx.AsyncClient(transport=asgi, base_url="http://test") as api_client:
        # initial full snapshot
        await api_client.get("/worlds/abc/activation")
        # unchanged hash
        h1 = await api_client.get("/worlds/abc/activation/state_hash")
        assert h1.json() == {"state_hash": "h1"}
        h2 = await api_client.get("/worlds/abc/activation/state_hash")
        assert h2.json() == {"state_hash": "h1"}
        assert calls["snap"] == 1
        # divergence
        h3 = await api_client.get("/worlds/abc/activation/state_hash")
        assert h3.json() == {"state_hash": "h2"}
        await api_client.get("/worlds/abc/activation")
    await asgi.aclose()
    await client._client.aclose()
    assert calls["snap"] == 2


@pytest.mark.asyncio
async def test_status_reports_worldservice_breaker(fake_redis):
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    transport = httpx.MockTransport(handler)
    breaker = AsyncCircuitBreaker(max_failures=1)
    from qmtl.gateway import gateway_health

    gateway_health._STATUS_CACHE = None
    gateway_health._STATUS_CACHE_TS = 0.0

    client = WorldServiceClient(
        "http://world",
        budget=Budget(timeout=0.1, retries=0),
        client=httpx.AsyncClient(transport=transport),
        breaker=breaker,
    )
    app = create_app(
        redis_client=fake_redis,
        database=FakeDB(),
        world_client=client,
        enable_background=False,
    )
    asgi = httpx.ASGITransport(app=app, lifespan="on")
    async with httpx.AsyncClient(transport=asgi, base_url="http://test") as api_client:
        with pytest.raises(httpx.ConnectError):
            await api_client.get("/worlds/abc/decide")
        s = await api_client.get("/status")
    await asgi.aclose()
    await client._client.aclose()
    assert s.json()["worldservice"] == "open"


def _make_jwt(payload: dict) -> str:
    header = base64.urlsafe_b64encode(json.dumps({"alg": "none", "typ": "JWT"}).encode()).decode().rstrip("=")
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    return f"{header}.{body}."


@pytest.mark.asyncio
async def test_identity_headers_forwarded(fake_redis):
    captured: dict[str, str] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured.update({"sub": request.headers.get("X-Caller-Sub"), "claims": request.headers.get("X-Caller-Claims")})
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(handler)
    client = WorldServiceClient("http://world", client=httpx.AsyncClient(transport=transport))
    app = create_app(
        redis_client=fake_redis,
        database=FakeDB(),
        world_client=client,
        enable_background=False,
    )
    asgi = httpx.ASGITransport(app=app, lifespan="on")
    token = _make_jwt({"sub": "alice", "role": "admin"})
    async with httpx.AsyncClient(transport=asgi, base_url="http://test") as api_client:
        await api_client.get("/worlds/abc/decide", headers={"Authorization": f"Bearer {token}"})
    await asgi.aclose()
    await client._client.aclose()
    assert captured["sub"] == "alice"
    claims = json.loads(captured["claims"])
    assert claims["role"] == "admin"


@pytest.mark.asyncio
async def test_identity_headers_absent_without_jwt(fake_redis):
    captured: dict[str, str] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured.update(request.headers)
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(handler)
    client = WorldServiceClient("http://world", client=httpx.AsyncClient(transport=transport))
    app = create_app(
        redis_client=fake_redis,
        database=FakeDB(),
        world_client=client,
        enable_background=False,
    )
    asgi = httpx.ASGITransport(app=app, lifespan="on")
    async with httpx.AsyncClient(transport=asgi, base_url="http://test") as api_client:
        await api_client.get("/worlds/abc/decide")
    await asgi.aclose()
    await client._client.aclose()
    assert "X-Caller-Sub" not in captured
    assert "X-Caller-Claims" not in captured


@pytest.mark.asyncio
async def test_identity_headers_malformed_jwt(fake_redis):
    captured: dict[str, str] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured.update(request.headers)
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(handler)
    client = WorldServiceClient("http://world", client=httpx.AsyncClient(transport=transport))
    app = create_app(
        redis_client=fake_redis,
        database=FakeDB(),
        world_client=client,
        enable_background=False,
    )
    asgi = httpx.ASGITransport(app=app, lifespan="on")
    async with httpx.AsyncClient(transport=asgi, base_url="http://test") as api_client:
        await api_client.get(
            "/worlds/abc/decide", headers={"Authorization": "Bearer not.a.jwt"}
        )
    await asgi.aclose()
    await client._client.aclose()
    assert "X-Caller-Sub" not in captured
    assert "X-Caller-Claims" not in captured
