from __future__ import annotations

import json

import httpx
import pytest

from qmtl.foundation.common import AsyncCircuitBreaker
from qmtl.services.gateway.api import create_app
from qmtl.services.gateway.world_client import Budget
from tests.services.gateway.helpers import make_jwt


@pytest.mark.asyncio
async def test_world_routes_require_world_client(
    fake_redis, gateway_stub_db, asgi_client_factory
) -> None:
    app = create_app(
        redis_client=fake_redis,
        database=gateway_stub_db,
        world_client=None,
        enable_background=False,
    )

    async with asgi_client_factory(app) as api_client:
        resp = await api_client.get("/worlds")

    assert resp.status_code == 503
    assert resp.json() == {"detail": "WorldService disabled"}


@pytest.mark.asyncio
async def test_world_proxy_sets_correlation_header(gateway_app_factory) -> None:
    captured: dict[str, str | None] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["cid"] = request.headers.get("X-Correlation-ID")
        return httpx.Response(200, json={"ok": True})

    async with gateway_app_factory(handler) as ctx:
        resp = await ctx.client.get("/worlds/abc")

    assert resp.status_code == 200
    assert resp.headers["X-Correlation-ID"]
    assert resp.headers["X-Correlation-ID"] == captured.get("cid")


@pytest.mark.asyncio
async def test_live_guard(gateway_app_factory) -> None:
    call_count = {"n": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/apply"):
            call_count["n"] += 1
            return httpx.Response(200, json={"ok": True})
        raise AssertionError("unexpected path")

    async with gateway_app_factory(handler) as ctx:
        r1 = await ctx.client.post("/worlds/abc/apply", json={})
        r2 = await ctx.client.post(
            "/worlds/abc/apply", json={}, headers={"X-Allow-Live": "true"}
        )

    assert r1.status_code == 403
    assert r2.status_code == 200
    assert call_count["n"] == 1


@pytest.mark.asyncio
async def test_live_guard_disabled(gateway_app_factory) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/apply"):
            return httpx.Response(200, json={"ok": True})
        raise AssertionError("unexpected path")

    async with gateway_app_factory(
        handler, app_kwargs={"enforce_live_guard": False}
    ) as ctx:
        resp = await ctx.client.post("/worlds/abc/apply", json={})

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_status_reports_worldservice_breaker(
    gateway_app_factory, reset_gateway_metrics
) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    breaker = AsyncCircuitBreaker(max_failures=1)
    from qmtl.services.gateway import gateway_health

    gateway_health._STATUS_CACHE = None
    gateway_health._STATUS_CACHE_TS = 0.0

    async with gateway_app_factory(
        handler,
        world_client_kwargs={
            "budget": Budget(timeout=0.1, retries=0),
            "breaker": breaker,
        },
    ) as ctx:
        with pytest.raises(httpx.ConnectError):
            await ctx.client.get("/worlds/abc/decide")
        status = await ctx.client.get("/status")

    assert status.json()["worldservice"] == "open"


@pytest.mark.asyncio
async def test_identity_headers_forwarded(gateway_app_factory) -> None:
    captured: dict[str, str] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured.update(
            {
                "sub": request.headers.get("X-Caller-Sub"),
                "claims": request.headers.get("X-Caller-Claims"),
            }
        )
        return httpx.Response(200, json={"ok": True})

    token = make_jwt({"sub": "alice", "role": "admin"})

    async with gateway_app_factory(handler) as ctx:
        await ctx.client.get(
            "/worlds/abc/decide",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert captured["sub"] == "alice"
    claims = json.loads(captured["claims"])
    assert claims["role"] == "admin"


@pytest.mark.asyncio
async def test_identity_headers_absent_without_jwt(gateway_app_factory) -> None:
    captured: dict[str, str] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured.update(request.headers)
        return httpx.Response(200, json={"ok": True})

    async with gateway_app_factory(handler) as ctx:
        await ctx.client.get("/worlds/abc/decide")

    assert "X-Caller-Sub" not in captured
    assert "X-Caller-Claims" not in captured


@pytest.mark.asyncio
async def test_identity_headers_malformed_jwt(gateway_app_factory) -> None:
    captured: dict[str, str] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured.update(request.headers)
        return httpx.Response(200, json={"ok": True})

    async with gateway_app_factory(handler) as ctx:
        await ctx.client.get(
            "/worlds/abc/decide",
            headers={"Authorization": "Bearer not.a.jwt"},
        )

    assert "X-Caller-Sub" not in captured
    assert "X-Caller-Claims" not in captured
