import json

import httpx
import pytest

from qmtl.services.gateway import metrics
from qmtl.services.gateway.world_client import WorldServiceClient


@pytest.mark.asyncio
async def test_request_json_success_returns_payload() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/worlds"
        return httpx.Response(200, json={"items": ["alpha"]})

    transport = httpx.MockTransport(handler)
    client = WorldServiceClient(
        "http://world",
        client=httpx.AsyncClient(transport=transport),
    )

    try:
        payload = await client.list_worlds()
        assert payload == {"items": ["alpha"]}
    finally:
        await client._client.aclose()


@pytest.mark.asyncio
async def test_request_json_propagates_http_errors() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    transport = httpx.MockTransport(handler)
    client = WorldServiceClient(
        "http://world",
        client=httpx.AsyncClient(transport=transport),
    )

    try:
        with pytest.raises(httpx.HTTPStatusError):
            await client.list_worlds()
    finally:
        await client._client.aclose()


@pytest.mark.asyncio
async def test_post_rebalance_plan_sets_schema_version() -> None:
    recorded: list[dict] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path != "/rebalancing/plan":
            raise AssertionError("unexpected path")
        recorded.append(json.loads(request.content))
        return httpx.Response(200, json={"per_world": {}, "global_deltas": []})

    transport = httpx.MockTransport(handler)
    client = WorldServiceClient(
        "http://world",
        client=httpx.AsyncClient(transport=transport),
    )

    try:
        await client.post_rebalance_plan(
            {"total_equity": 1000.0},
            schema_version=2,
        )
    finally:
        await client._client.aclose()

    assert recorded
    assert recorded[0]["schema_version"] == 2


@pytest.mark.asyncio
async def test_post_rebalance_plan_falls_back_when_schema_rejected() -> None:
    attempts: list[int] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path != "/rebalancing/plan":
            raise AssertionError("unexpected path")
        body = json.loads(request.content)
        attempts.append(body.get("schema_version", 0))
        if len(attempts) == 1:
            return httpx.Response(400, json={"detail": "unsupported schema"})
        return httpx.Response(200, json={"per_world": {}, "global_deltas": []})

    transport = httpx.MockTransport(handler)
    client = WorldServiceClient(
        "http://world",
        client=httpx.AsyncClient(transport=transport),
    )

    try:
        await client.post_rebalance_plan(
            {"total_equity": 1000.0},
            schema_version=2,
            fallback_schema_version=1,
        )
    finally:
        await client._client.aclose()

    assert attempts == [2, 1]


@pytest.mark.asyncio
async def test_get_decide_returns_cached_payload_on_backend_error() -> None:
    metrics.reset_metrics()
    calls = {"count": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/decide"):
            calls["count"] += 1
            if calls["count"] == 1:
                return httpx.Response(
                    200,
                    json={"decision": "ok"},
                    headers={"Cache-Control": "max-age=60"},
                )
            return httpx.Response(500)
        raise AssertionError("unexpected path")

    transport = httpx.MockTransport(handler)
    client = WorldServiceClient(
        "http://world",
        client=httpx.AsyncClient(transport=transport),
    )

    try:
        first, stale_first = await client.get_decide("w1")
        assert first == {"decision": "ok"}
        assert stale_first is False

        # Force cache expiration to trigger a new request that will fail.
        client._decision_cache.expire("w1")

        second, stale_second = await client.get_decide("w1")
        assert second == {"decision": "ok"}
        assert stale_second is True
        assert metrics.worlds_stale_responses_total._value.get() == 1
    finally:
        await client._client.aclose()


@pytest.mark.asyncio
async def test_post_rebalance_plan_includes_schema_version() -> None:
    observed: list[dict] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode() or "{}")
        observed.append(body)
        assert body.get("schema_version") == 2
        return httpx.Response(200, json={"per_world": {}})

    transport = httpx.MockTransport(handler)
    client = WorldServiceClient(
        "http://world",
        client=httpx.AsyncClient(transport=transport),
        rebalance_schema_version=2,
    )

    try:
        result = await client.post_rebalance_plan({"total_equity": 1})
        assert result == {"per_world": {}}
        assert observed and observed[0]["schema_version"] == 2
    finally:
        await client._client.aclose()


@pytest.mark.asyncio
async def test_post_rebalance_plan_falls_back_to_v1_on_client_error() -> None:
    attempts: list[dict] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode() or "{}")
        attempts.append(body)
        if len(attempts) == 1:
            assert body.get("schema_version") == 2
            return httpx.Response(400, json={"detail": "unsupported"})
        assert "schema_version" not in body
        return httpx.Response(200, json={"per_world": {"world-a": {}}})

    transport = httpx.MockTransport(handler)
    client = WorldServiceClient(
        "http://world",
        client=httpx.AsyncClient(transport=transport),
        rebalance_schema_version=2,
    )

    try:
        result = await client.post_rebalance_plan({"total_equity": 1})
        assert result == {"per_world": {"world-a": {}}}
        assert len(attempts) == 2
        assert attempts[1].get("schema_version") is None
    finally:
        await client._client.aclose()
