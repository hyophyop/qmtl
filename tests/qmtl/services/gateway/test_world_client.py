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
    attempts: list[int | None] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path != "/rebalancing/plan":
            raise AssertionError("unexpected path")
        body = json.loads(request.content)
        attempts.append(body.get("schema_version"))
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

    assert attempts == [2, None]


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
async def test_get_decide_as_of_forwards_query_and_scopes_cache() -> None:
    seen_params: list[dict[str, str]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/decide"):
            seen_params.append(dict(request.url.params))
            return httpx.Response(
                200,
                json={"decision": f"ok-{len(seen_params)}"},
                headers={"Cache-Control": "max-age=60"},
            )
        raise AssertionError("unexpected path")

    transport = httpx.MockTransport(handler)
    client = WorldServiceClient(
        "http://world",
        client=httpx.AsyncClient(transport=transport),
    )

    try:
        first, stale_first = await client.get_decide("w1", as_of="2025-01-01T00:00:00Z")
        second, stale_second = await client.get_decide("w1", as_of="2025-01-01T00:00:00Z")
        third, stale_third = await client.get_decide("w1", as_of="2025-01-02T00:00:00Z")
    finally:
        await client._client.aclose()

    assert first == {"decision": "ok-1"}
    assert stale_first is False
    assert second == {"decision": "ok-1"}
    assert stale_second is False
    assert third == {"decision": "ok-2"}
    assert stale_third is False
    assert seen_params == [
        {"as_of": "2025-01-01T00:00:00Z"},
        {"as_of": "2025-01-02T00:00:00Z"},
    ]


@pytest.mark.asyncio
async def test_get_activation_returns_inactive_failsafe_on_stale_backend_error() -> None:
    metrics.reset_metrics()
    calls = {"count": 0}
    activation_payload = {
        "world_id": "w1",
        "strategy_id": "s1",
        "side": "long",
        "active": True,
        "weight": 1.0,
        "etag": "abc",
        "ts": "2025-01-01T00:00:00Z",
    }

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/activation"):
            calls["count"] += 1
            if calls["count"] == 1:
                assert request.headers.get("If-None-Match") is None
                return httpx.Response(
                    200,
                    json=activation_payload,
                    headers={"ETag": "abc"},
                )
            assert request.headers.get("If-None-Match") == "abc"
            return httpx.Response(500)
        raise AssertionError("unexpected path")

    transport = httpx.MockTransport(handler)
    client = WorldServiceClient(
        "http://world",
        client=httpx.AsyncClient(transport=transport),
    )

    try:
        first, stale_first = await client.get_activation("w1", "s1", "long")
        second, stale_second = await client.get_activation("w1", "s1", "long")
    finally:
        await client._client.aclose()

    assert first == activation_payload
    assert stale_first is False
    assert second["world_id"] == "w1"
    assert second["strategy_id"] == "s1"
    assert second["side"] == "long"
    assert second["active"] is False
    assert second["weight"] == 0.0
    assert second["effective_mode"] == "compute-only"
    assert second["execution_domain"] == "backtest"
    assert stale_second is True
    assert first["active"] is True
    assert metrics.worlds_stale_responses_total._value.get() == 1


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
