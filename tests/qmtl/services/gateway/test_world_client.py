import json
from collections.abc import Callable

import httpx
import pytest

from qmtl.services.gateway import metrics
from qmtl.services.gateway.world_client import WorldServiceClient


RequestCheck = Callable[[httpx.Request], None]


def _sequenced_transport(
    *,
    expected_path_suffix: str,
    responses: list[httpx.Response],
    request_checks: list[RequestCheck],
) -> httpx.MockTransport:
    assert len(responses) == len(request_checks)
    state = {"index": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith(expected_path_suffix)
        idx = state["index"]
        state["index"] += 1
        assert idx < len(responses), "unexpected request count"
        request_checks[idx](request)
        return responses[idx]

    return httpx.MockTransport(handler)


def _noop_request_check(_: httpx.Request) -> None:
    return None


def _header_is_absent(name: str) -> RequestCheck:
    def check(request: httpx.Request) -> None:
        assert request.headers.get(name) is None

    return check


def _header_equals(name: str, expected_value: str) -> RequestCheck:
    def check(request: httpx.Request) -> None:
        assert request.headers.get(name) == expected_value

    return check


def _assert_live_decision_payload(payload: dict, stale: bool) -> None:
    assert stale is False
    assert payload["effective_mode"] == "live"
    assert payload["execution_domain"] == "live"


def _assert_stale_decision_downgrade(payload: dict, stale: bool) -> None:
    assert stale is True
    assert payload["world_id"] == "w-live"
    assert payload["effective_mode"] == "compute-only"
    assert payload["execution_domain"] == "backtest"
    assert payload["compute_context"]["execution_domain"] == "backtest"
    assert "safe_mode" not in payload["compute_context"]


def _assert_initial_activation(payload: dict, stale: bool, expected: dict) -> None:
    assert payload == expected
    assert stale is False
    assert payload["active"] is True


def _assert_stale_activation_downgrade(payload: dict, stale: bool) -> None:
    assert stale is True
    expected = {
        "world_id": "w1",
        "strategy_id": "s1",
        "side": "long",
        "active": False,
        "weight": 0.0,
        "effective_mode": "compute-only",
        "execution_domain": "backtest",
    }
    assert {key: payload[key] for key in expected} == expected
    compute_context = payload["compute_context"]
    assert compute_context["execution_domain"] == "backtest"
    assert compute_context["downgraded"] is True
    assert compute_context["downgrade_reason"] == "missing_as_of"
    assert compute_context["safe_mode"] is True


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
async def test_get_decide_stale_response_downgrades_live_mode_to_compute_only() -> None:
    metrics.reset_metrics()
    decision_payload = {
        "world_id": "w-live",
        "policy_version": 7,
        "effective_mode": "live",
        "as_of": "2025-01-01T00:00:00Z",
        "ttl": "300s",
        "etag": "w-live:v7",
    }
    transport = _sequenced_transport(
        expected_path_suffix="/decide",
        responses=[
            httpx.Response(
                200,
                json=decision_payload,
                headers={"Cache-Control": "max-age=60"},
            ),
            httpx.Response(500),
        ],
        request_checks=[_noop_request_check, _noop_request_check],
    )
    client = WorldServiceClient(
        "http://world",
        client=httpx.AsyncClient(transport=transport),
    )

    try:
        first, stale_first = await client.get_decide("w-live")
        _assert_live_decision_payload(first, stale_first)

        client._decision_cache.expire("w-live")

        second, stale_second = await client.get_decide("w-live")
    finally:
        await client._client.aclose()

    _assert_stale_decision_downgrade(second, stale_second)
    assert metrics.worlds_stale_responses_total._value.get() == 1


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
    activation_payload = {
        "world_id": "w1",
        "strategy_id": "s1",
        "side": "long",
        "active": True,
        "weight": 1.0,
        "etag": "abc",
        "ts": "2025-01-01T00:00:00Z",
    }
    transport = _sequenced_transport(
        expected_path_suffix="/activation",
        responses=[
            httpx.Response(
                200,
                json=activation_payload,
                headers={"ETag": "abc"},
            ),
            httpx.Response(500),
        ],
        request_checks=[
            _header_is_absent("If-None-Match"),
            _header_equals("If-None-Match", "abc"),
        ],
    )
    client = WorldServiceClient(
        "http://world",
        client=httpx.AsyncClient(transport=transport),
    )

    try:
        first, stale_first = await client.get_activation("w1", "s1", "long")
        second, stale_second = await client.get_activation("w1", "s1", "long")
    finally:
        await client._client.aclose()

    _assert_initial_activation(first, stale_first, activation_payload)
    _assert_stale_activation_downgrade(second, stale_second)
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
