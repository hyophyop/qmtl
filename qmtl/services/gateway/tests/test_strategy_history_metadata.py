from __future__ import annotations

import json

import httpx
import pytest

from tests.qmtl.services.gateway.helpers import gateway_app


@pytest.mark.asyncio
async def test_post_strategy_history_updates_context(fake_redis):
    strategy_id = "strategy-123"
    await fake_redis.hset(f"strategy:{strategy_id}", mapping={"dag": "{}", "hash": "abc"})

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=404)

    payload = {
        "node_id": "node-1",
        "interval": 60,
        "rows": 2,
        "coverage_bounds": [0, 120],
        "conformance_flags": {"missing": 1},
        "conformance_warnings": ["gap"],
        "dataset_fingerprint": "fp-abc",
        "as_of": "2025-01-01T00:00:00Z",
        "world_id": "world-1",
        "execution_domain": "live",
        "artifact": {
            "dataset_fingerprint": "fp-abc",
            "as_of": "2025-01-01T00:00:00Z",
            "rows": 2,
            "uri": "local://artifact",
        },
    }

    async with gateway_app(handler, redis_client=fake_redis) as ctx:
        resp = await ctx.client.post(
            f"/strategies/{strategy_id}/history",
            json=payload,
        )
        assert resp.status_code == 204

    stored = await fake_redis.hgetall(f"strategy:{strategy_id}")
    assert stored["compute_dataset_fingerprint"] == "fp-abc"
    assert stored["compute_as_of"] == "2025-01-01T00:00:00Z"
    assert stored["compute_world_id"] == "world-1"
    assert stored["compute_execution_domain"] == "live"
    meta = json.loads(stored[f"seamless:{payload['node_id']}"])
    assert meta["dataset_fingerprint"] == "fp-abc"
    assert meta["coverage_bounds"] == [0, 120]
    assert meta["artifact"]["uri"] == "local://artifact"


@pytest.mark.asyncio
async def test_post_strategy_history_missing_strategy(fake_redis):
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=404)

    async with gateway_app(handler, redis_client=fake_redis) as ctx:
        resp = await ctx.client.post(
            "/strategies/unknown/history",
            json={"node_id": "n1", "interval": 60},
        )
        assert resp.status_code == 404


@pytest.mark.asyncio
async def test_post_strategy_history_forwards_to_worldservice(fake_redis):
    strategy_id = "strategy-ws"
    await fake_redis.hset(f"strategy:{strategy_id}", mapping={"dag": "{}", "hash": "xyz"})

    calls: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(status_code=204)

    payload = {
        "node_id": "node-ws",
        "interval": 30,
        "rows": 1,
        "coverage_bounds": [100, 130],
        "dataset_fingerprint": "fp-world",
        "as_of": "2025-02-01T00:00:00Z",
        "world_id": "world-1",
        "execution_domain": "live",
    }

    async with gateway_app(handler, redis_client=fake_redis) as ctx:
        resp = await ctx.client.post(
            f"/strategies/{strategy_id}/history",
            json=payload,
        )
        assert resp.status_code == 204

    assert calls
    request = calls[0]
    assert request.url.path.endswith("/worlds/world-1/history")
    body = json.loads(request.content.decode())
    assert body["strategy_id"] == strategy_id
    assert body["dataset_fingerprint"] == "fp-world"
    assert body["coverage_bounds"] == [100, 130]
