from __future__ import annotations

import httpx
import pytest

from qmtl.services.gateway import metrics


@pytest.mark.asyncio
async def test_activation_etag_cache(gateway_app_factory) -> None:
    call_count = {"n": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/activation"):
            if request.headers.get("If-None-Match") == "abc":
                return httpx.Response(304, headers={"ETag": "abc"})
            call_count["n"] += 1
            return httpx.Response(
                200,
                json={"a": call_count["n"]},
                headers={"ETag": "abc"},
            )
        raise AssertionError("unexpected path")

    async with gateway_app_factory(handler) as ctx:
        params = {"strategy_id": "s", "side": "long"}
        r1 = await ctx.client.get("/worlds/abc/activation", params=params)
        r2 = await ctx.client.get("/worlds/abc/activation", params=params)

    assert r1.json() == {"a": 1}
    assert r2.json() == {"a": 1}
    assert call_count["n"] == 1


@pytest.mark.asyncio
async def test_activation_stale_on_backend_error(
    gateway_app_factory, reset_gateway_metrics
) -> None:
    calls = {"n": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/activation"):
            calls["n"] += 1
            if calls["n"] == 1:
                return httpx.Response(
                    200,
                    json={"a": 1},
                    headers={"ETag": "abc"},
                )
            return httpx.Response(500)
        raise AssertionError("unexpected path")

    async with gateway_app_factory(handler) as ctx:
        params = {"strategy_id": "s", "side": "long"}
        r1 = await ctx.client.get("/worlds/abc/activation", params=params)
        r2 = await ctx.client.get("/worlds/abc/activation", params=params)

    assert r1.json() == {"a": 1}
    assert r2.json() == {"a": 1}
    assert r2.headers["X-Stale"] == "true"
    assert r2.headers["Warning"] == "110 - Response is stale"
    assert metrics.worlds_stale_responses_total._value.get() == 1


@pytest.mark.asyncio
async def test_activation_backend_error_no_cache(
    gateway_app_factory, reset_gateway_metrics
) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/activation"):
            return httpx.Response(500)
        raise AssertionError("unexpected path")

    async with gateway_app_factory(handler) as ctx:
        with pytest.raises(httpx.HTTPStatusError):
            await ctx.client.get(
                "/worlds/abc/activation",
                params={"strategy_id": "s", "side": "long"},
            )

    assert metrics.worlds_stale_responses_total._value.get() == 0


@pytest.mark.asyncio
async def test_state_hash_probe_divergence(gateway_app_factory) -> None:
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

    async with gateway_app_factory(handler) as ctx:
        await ctx.client.get(
            "/worlds/abc/activation",
            params={"strategy_id": "s", "side": "long"},
        )
        h1 = await ctx.client.get("/worlds/abc/activation/state_hash")
        assert h1.json() == {"state_hash": "h1"}
        h2 = await ctx.client.get("/worlds/abc/activation/state_hash")
        assert h2.json() == {"state_hash": "h1"}
        assert calls["snap"] == 1
        h3 = await ctx.client.get("/worlds/abc/activation/state_hash")
        assert h3.json() == {"state_hash": "h2"}
        await ctx.client.get(
            "/worlds/abc/activation",
            params={"strategy_id": "s", "side": "long"},
        )

    assert calls["snap"] == 2
