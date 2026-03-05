from __future__ import annotations

import json

import httpx
import pytest


def _default_payload():
    return {
        "total_equity": 1_000_000.0,
        "world_alloc_before": {"w1": 1.0},
        "world_alloc_after": {"w1": 1.0},
        "positions": [
            {
                "world_id": "w1",
                "strategy_id": "s1",
                "symbol": "BTCUSDT",
                "qty": 2.0,
                "mark": 30_000.0,
                "venue": "binance",
            }
        ],
    }


@pytest.mark.asyncio
async def test_execute_contract_v1_plan(gateway_app_factory):
    """Gateway should consume schema v1 plans without optional metadata."""

    plan_fixture = {
        "schema_version": 1,
        "per_world": {
            "w1": {
                "world_id": "w1",
                "scale_world": 1.0,
                "scale_by_strategy": {"s1": 0.75},
                "deltas": [
                    {"symbol": "BTCUSDT", "delta_qty": -0.5, "venue": "binance"},
                    {"symbol": "ETHUSDT", "delta_qty": 1.0, "venue": None},
                ],
            }
        },
        "global_deltas": [],
    }

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/rebalancing/plan":
            body = json.loads(request.content.decode())
            assert body.get("schema_version") in (None, 1)
            return httpx.Response(200, json=plan_fixture)
        if request.method == "GET" and request.url.path == "/worlds/w1":
            return httpx.Response(200, json={"world": {"id": "w1", "mode": "simulate"}})
        if request.method == "GET" and request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok"})
        raise AssertionError(f"Unexpected path {request.url.path}")

    async with gateway_app_factory(handler) as ctx:
        resp = await ctx.client.post("/rebalancing/execute", json=_default_payload())

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["rebalance_schema_version"] == 1
    assert payload["alpha_metrics_capable"] is False
    assert "orders_per_world" in payload and "w1" in payload["orders_per_world"]
    orders = payload["orders_per_world"]["w1"]
    symbols = {order["symbol"] for order in orders}
    assert symbols == {"BTCUSDT", "ETHUSDT"}


@pytest.mark.asyncio
async def test_execute_contract_v2_plan(gateway_app_factory):
    """Gateway should request schema v2 and tolerate optional envelopes."""

    plan_fixture = {
        "schema_version": 2,
        "per_world": {
            "w1": {
                "world_id": "w1",
                "scale_world": 0.9,
                "scale_by_strategy": {"s1": 0.6},
                "deltas": [
                    {"symbol": "BTCUSDT", "delta_qty": -1.0, "venue": "binance"},
                ],
            }
        },
        "global_deltas": [],
        "alpha_metrics": {
            "per_world": {"w1": {"alpha_performance.sharpe": 0.5}},
            "per_strategy": {},
        },
        "rebalance_intent": {"meta": {"ticket": "gw-1514"}},
    }

    observed_versions: list[int | None] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/rebalancing/plan":
            body = json.loads(request.content.decode())
            observed_versions.append(body.get("schema_version"))
            return httpx.Response(200, json=plan_fixture)
        if request.method == "GET" and request.url.path == "/worlds/w1":
            return httpx.Response(200, json={"world": {"id": "w1", "mode": "simulate"}})
        if request.method == "GET" and request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok"})
        raise AssertionError(f"Unexpected path {request.url.path}")

    async with gateway_app_factory(
        handler,
        app_kwargs={"rebalance_schema_version": 2, "alpha_metrics_capable": True},
    ) as ctx:
        resp = await ctx.client.post("/rebalancing/execute", json=_default_payload())

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["rebalance_schema_version"] == 2
    assert payload["alpha_metrics_capable"] is True
    assert observed_versions == [2]


@pytest.mark.asyncio
async def test_execute_contract_overlay_plan_uses_overlay_deltas(gateway_app_factory):
    """Gateway should translate overlay deltas into per-world execution orders."""

    plan_fixture = {
        "schema_version": 2,
        "per_world": {},
        "global_deltas": [],
        "overlay_deltas": [
            {"symbol": "BTCUSDT_PERP", "delta_qty": 0.5, "venue": None},
        ],
    }

    payload = {
        **_default_payload(),
        "mode": "overlay",
        "overlay": {
            "instrument_by_world": {"w1": "BTCUSDT_PERP"},
            "price_by_symbol": {"BTCUSDT_PERP": 100_000.0},
            "min_order_notional": 10.0,
        },
    }

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/rebalancing/plan":
            body = json.loads(request.content.decode())
            assert body["mode"] == "overlay"
            return httpx.Response(200, json=plan_fixture)
        raise AssertionError(f"Unexpected path {request.url.path}")

    async with gateway_app_factory(
        handler,
        app_kwargs={"rebalance_schema_version": 2},
    ) as ctx:
        resp = await ctx.client.post("/rebalancing/execute", json=payload)

    assert resp.status_code == 200
    body = resp.json()
    assert body["overlay_deltas"] == plan_fixture["overlay_deltas"]
    assert body["orders_per_world"] == {
        "w1": [
            {
                "symbol": "BTCUSDT_PERP",
                "quantity": 0.5,
                "side": "buy",
                "time_in_force": "GTC",
            }
        ]
    }
    assert "orders_global" not in body


@pytest.mark.asyncio
async def test_execute_contract_reports_downgraded_version_on_fallback(
    gateway_app_factory,
):
    """When WorldService rejects v2, Gateway should downgrade the reported version."""

    plan_fixture_v1 = {
        "schema_version": 1,
        "per_world": {
            "w1": {
                "world_id": "w1",
                "scale_world": 1.0,
                "scale_by_strategy": {},
                "deltas": [],
            }
        },
        "global_deltas": [],
    }

    observed_versions: list[int | None] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/rebalancing/plan":
            body = json.loads(request.content.decode())
            observed_versions.append(body.get("schema_version"))
            if len(observed_versions) == 1:
                return httpx.Response(400, json={"detail": "unsupported schema"})
            return httpx.Response(200, json=plan_fixture_v1)
        if request.method == "GET" and request.url.path == "/worlds/w1":
            return httpx.Response(200, json={"world": {"id": "w1", "mode": "simulate"}})
        if request.method == "GET" and request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok"})
        raise AssertionError(f"Unexpected path {request.url.path}")

    async with gateway_app_factory(
        handler,
        app_kwargs={"rebalance_schema_version": 2, "alpha_metrics_capable": True},
    ) as ctx:
        resp = await ctx.client.post("/rebalancing/execute", json=_default_payload())

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["rebalance_schema_version"] == 1
    assert payload["alpha_metrics_capable"] is False
    assert observed_versions == [2, None]


@pytest.mark.asyncio
async def test_execute_contract_overlay_mode_returns_per_world_orders(gateway_app_factory):
    plan_fixture = {
        "schema_version": 2,
        "per_world": {},
        "global_deltas": [],
        "overlay_deltas": [
            {"symbol": "ES_PERP", "delta_qty": 3.0, "venue": "cme"},
        ],
    }

    payload = _default_payload()
    payload["mode"] = "overlay"
    payload["overlay"] = {
        "instrument_by_world": {"w1": "ES_PERP"},
        "price_by_symbol": {"ES_PERP": 5000.0},
    }

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/rebalancing/plan":
            return httpx.Response(200, json=plan_fixture)
        if request.method == "GET" and request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok"})
        raise AssertionError(f"Unexpected path {request.url.path}")

    async with gateway_app_factory(
        handler,
        app_kwargs={"rebalance_schema_version": 2, "alpha_metrics_capable": True},
    ) as ctx:
        resp = await ctx.client.post("/rebalancing/execute", json=payload)

    assert resp.status_code == 200
    body = resp.json()
    assert body["orders_per_world"]["w1"][0]["symbol"] == "ES_PERP"
    assert body["overlay_deltas"][0]["symbol"] == "ES_PERP"
