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
