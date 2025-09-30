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
