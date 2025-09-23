from __future__ import annotations

import httpx
import pytest

from qmtl.foundation.common.compute_context import DowngradeReason
from qmtl.services.gateway import metrics


@pytest.mark.asyncio
async def test_decide_ttl_cache(gateway_app_factory, reset_gateway_metrics) -> None:
    call_count = {"n": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/decide"):
            call_count["n"] += 1
            return httpx.Response(
                200,
                json={"v": call_count["n"]},
                headers={"Cache-Control": "max-age=60"},
            )
        raise AssertionError("unexpected path")

    async with gateway_app_factory(handler) as ctx:
        r1 = await ctx.client.get("/worlds/abc/decide")
        r2 = await ctx.client.get("/worlds/abc/decide")

    assert r1.json() == {"v": 1}
    assert r2.json() == {"v": 1}
    assert call_count["n"] == 1
    assert metrics.worlds_cache_hit_ratio._value.get() == pytest.approx(0.5)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mode, expected",
    [
        ("validate", "backtest"),
        ("compute-only", "backtest"),
        ("paper", "dryrun"),
        ("live", "live"),
        ("shadow", "shadow"),
        ("ACTIVE", "live"),
        ("unknown", "backtest"),
    ],
)
async def test_decide_compute_context_mapping(
    gateway_app_factory, reset_gateway_metrics, mode, expected
) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/decide"):
            body = {
                "world_id": "world-alpha",
                "policy_version": 3,
                "effective_mode": mode,
                "as_of": "2025-01-01T00:00:00Z",
                "ttl": "300s",
                "etag": "w:world-alpha:v3",
                "partition": "tenant-a",
                "dataset_fingerprint": "lake:blake3:abc",
            }
            return httpx.Response(200, json=body)
        raise AssertionError("unexpected path")

    async with gateway_app_factory(handler) as ctx:
        resp = await ctx.client.get("/worlds/world-alpha/decide")

    data = resp.json()
    assert data["execution_domain"] == expected
    context = data["compute_context"]
    assert context["world_id"] == "world-alpha"
    assert context["execution_domain"] == expected
    assert context["as_of"] == "2025-01-01T00:00:00Z"
    assert context["partition"] == "tenant-a"
    assert context["dataset_fingerprint"] == "lake:blake3:abc"
    assert "downgraded" not in context


@pytest.mark.asyncio
async def test_decide_compute_context_downgrade_missing_as_of(
    gateway_app_factory, reset_gateway_metrics
) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/decide"):
            body = {
                "world_id": "world-beta",
                "policy_version": 1,
                "effective_mode": "paper",
                "ttl": "300s",
                "etag": "w:world-beta:v1",
            }
            return httpx.Response(200, json=body)
        raise AssertionError("unexpected path")

    async with gateway_app_factory(handler) as ctx:
        resp = await ctx.client.get("/worlds/world-beta/decide")

    data = resp.json()
    assert data["execution_domain"] == "backtest"
    context = data["compute_context"]
    assert context["execution_domain"] == "backtest"
    assert context["as_of"] is None
    assert context["downgraded"] is True
    assert context["downgrade_reason"] == DowngradeReason.MISSING_AS_OF
    metric_value = (
        metrics.worlds_compute_context_downgrade_total.labels(
            reason=DowngradeReason.MISSING_AS_OF.value
        )._value.get()
    )
    assert metric_value == 1


@pytest.mark.asyncio
async def test_decide_stale_on_backend_error(
    gateway_app_factory, reset_gateway_metrics
) -> None:
    calls = {"n": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/decide"):
            calls["n"] += 1
            if calls["n"] == 1:
                return httpx.Response(
                    200,
                    json={"v": 1},
                    headers={"Cache-Control": "max-age=60"},
                )
            return httpx.Response(500)
        raise AssertionError("unexpected path")

    async with gateway_app_factory(handler) as ctx:
        r1 = await ctx.client.get("/worlds/abc/decide")
        ctx.world_client._decision_cache.expire("abc")
        r2 = await ctx.client.get("/worlds/abc/decide")

    assert r1.json() == {"v": 1}
    assert r2.json() == {"v": 1}
    assert r2.headers["X-Stale"] == "true"
    assert r2.headers["Warning"] == "110 - Response is stale"
    assert metrics.worlds_stale_responses_total._value.get() == 1


@pytest.mark.asyncio
async def test_decide_backend_error_no_cache(
    gateway_app_factory, reset_gateway_metrics
) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/decide"):
            return httpx.Response(500)
        raise AssertionError("unexpected path")

    async with gateway_app_factory(handler) as ctx:
        with pytest.raises(httpx.HTTPStatusError):
            await ctx.client.get("/worlds/abc/decide")

    assert metrics.worlds_stale_responses_total._value.get() == 0


@pytest.mark.asyncio
async def test_decide_ttl_envelope_fallback(gateway_app_factory) -> None:
    calls = {"n": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/decide"):
            calls["n"] += 1
            return httpx.Response(200, json={"v": calls["n"], "ttl": "300s"})
        raise AssertionError("unexpected path")

    async with gateway_app_factory(handler) as ctx:
        r1 = await ctx.client.get("/worlds/abc/decide")
        r2 = await ctx.client.get("/worlds/abc/decide")

    assert r1.json() == {"v": 1, "ttl": "300s"}
    assert r2.json() == {"v": 1, "ttl": "300s"}
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_decide_ttl_zero_no_cache(gateway_app_factory) -> None:
    calls = {"n": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/decide"):
            calls["n"] += 1
            return httpx.Response(200, json={"v": calls["n"], "ttl": "0s"})
        raise AssertionError("unexpected path")

    async with gateway_app_factory(handler) as ctx:
        r1 = await ctx.client.get("/worlds/abc/decide")
        r2 = await ctx.client.get("/worlds/abc/decide")

    assert r1.json() == {"v": 1, "ttl": "0s"}
    assert r2.json() == {"v": 2, "ttl": "0s"}
    assert calls["n"] == 2
