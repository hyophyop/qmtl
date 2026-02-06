from __future__ import annotations

import httpx
import pytest

from qmtl.services.gateway import metrics


def _make_activation_stale_handler(
    calls: dict[str, int], activation_payload: dict[str, object]
):
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/activation"):
            calls["n"] += 1
            if calls["n"] == 1:
                return httpx.Response(
                    200,
                    json=activation_payload,
                    headers={"ETag": "abc"},
                )
            return httpx.Response(500)
        raise AssertionError("unexpected path")

    return handler


def _assert_stale_activation_response(response: httpx.Response) -> None:
    payload = response.json()
    assert {
        "world_id": payload["world_id"],
        "strategy_id": payload["strategy_id"],
        "side": payload["side"],
        "active": payload["active"],
        "weight": payload["weight"],
        "effective_mode": payload["effective_mode"],
        "execution_domain": payload["execution_domain"],
    } == {
        "world_id": "abc",
        "strategy_id": "s",
        "side": "long",
        "active": False,
        "weight": 0.0,
        "effective_mode": "compute-only",
        "execution_domain": "backtest",
    }
    assert {
        "execution_domain": payload["compute_context"]["execution_domain"],
        "downgraded": payload["compute_context"]["downgraded"],
        "downgrade_reason": payload["compute_context"]["downgrade_reason"],
        "safe_mode": payload["compute_context"]["safe_mode"],
    } == {
        "execution_domain": "backtest",
        "downgraded": True,
        "downgrade_reason": "missing_as_of",
        "safe_mode": True,
    }
    assert {
        "X-Stale": response.headers["X-Stale"],
        "Warning": response.headers["Warning"],
    } == {
        "X-Stale": "true",
        "Warning": "110 - Response is stale",
    }


def _assert_initial_activation_response(
    response: httpx.Response, activation_payload: dict[str, object]
) -> None:
    payload = response.json()
    assert {key: payload[key] for key in activation_payload} == activation_payload
    assert payload["execution_domain"] == "backtest"
    assert {
        "execution_domain": payload["compute_context"]["execution_domain"],
        "downgraded": payload["compute_context"]["downgraded"],
        "downgrade_reason": payload["compute_context"]["downgrade_reason"],
        "safe_mode": payload["compute_context"]["safe_mode"],
    } == {
        "execution_domain": "backtest",
        "downgraded": True,
        "downgrade_reason": "decision_unavailable",
        "safe_mode": True,
    }


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
    activation_payload = {
        "world_id": "abc",
        "strategy_id": "s",
        "side": "long",
        "active": True,
        "weight": 1.0,
        "etag": "abc",
        "ts": "2025-01-01T00:00:00Z",
    }

    async with gateway_app_factory(
        _make_activation_stale_handler(calls, activation_payload)
    ) as ctx:
        params = {"strategy_id": "s", "side": "long"}
        r1 = await ctx.client.get("/worlds/abc/activation", params=params)
        r2 = await ctx.client.get("/worlds/abc/activation", params=params)

    _assert_initial_activation_response(r1, activation_payload)
    _assert_stale_activation_response(r2)
    assert metrics.worlds_stale_responses_total._value.get() == 1


@pytest.mark.asyncio
async def test_activation_backend_error_no_cache(
    gateway_app_factory, reset_gateway_metrics
) -> None:
    captured: dict[str, str | None] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/activation"):
            captured["cid"] = request.headers.get("X-Correlation-ID")
            return httpx.Response(500)
        raise AssertionError("unexpected path")

    async with gateway_app_factory(handler) as ctx:
        resp = await ctx.client.get(
            "/worlds/abc/activation",
            params={"strategy_id": "s", "side": "long"},
        )

    assert resp.status_code == 500
    assert resp.json() == {"detail": "WorldService request failed"}
    assert resp.headers["X-Correlation-ID"]
    assert resp.headers["X-Correlation-ID"] == captured.get("cid")
    assert metrics.worlds_stale_responses_total._value.get() == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("effective_mode", "expected_domain"),
    [
        ("validate", "backtest"),
        ("compute-only", "backtest"),
        ("paper", "backtest"),
        ("live", "live"),
        ("shadow", "shadow"),
    ],
)
async def test_activation_execution_domain_augmentation(
    gateway_app_factory, effective_mode, expected_domain
) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/activation"):
            return httpx.Response(
                200,
                json={
                    "world_id": "w",
                    "strategy_id": "s",
                    "side": "long",
                    "effective_mode": effective_mode,
                },
                headers={"ETag": "etag"},
            )
        raise AssertionError("unexpected path")

    async with gateway_app_factory(handler) as ctx:
        resp = await ctx.client.get(
            "/worlds/w/activation",
            params={"strategy_id": "s", "side": "long"},
        )

    data = resp.json()
    assert data["effective_mode"] == effective_mode
    assert data["execution_domain"] == expected_domain


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
