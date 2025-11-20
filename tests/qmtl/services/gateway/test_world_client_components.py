"""Unit tests for reusable primitives in the WorldService proxy."""
from __future__ import annotations

import httpx
import pytest
from typing import cast

from qmtl.foundation.common import AsyncCircuitBreaker
from qmtl.foundation.common.compute_context import DowngradeReason
from qmtl.services.gateway.caches import ActivationCache, TTLCache
from qmtl.services.gateway.transport import BreakerRetryTransport
from qmtl.services.gateway.world_payloads import augment_decision_payload


class StubAsyncClient:
    """Deterministic httpx.AsyncClient stand-in for transport tests."""

    def __init__(self, outcomes: list[httpx.Response | Exception]) -> None:
        self._outcomes = list(outcomes)
        self.calls: list[tuple[str, str]] = []

    async def request(self, method: str, url: str, **_: object) -> httpx.Response:
        self.calls.append((method, url))
        if not self._outcomes:
            raise AssertionError("Unexpected request")
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def test_ttl_cache_tracks_freshness() -> None:
    clock = [1_000.0]
    cache = TTLCache[str](clock=lambda: clock[0])

    result = cache.lookup("alpha")
    assert result.present is False

    cache.set("alpha", "payload", ttl=10)
    fresh = cache.lookup("alpha")
    assert fresh.present is True
    assert fresh.fresh is True
    assert fresh.value == "payload"

    clock[0] += 15
    stale = cache.lookup("alpha")
    assert stale.present is True
    assert stale.fresh is False
    assert stale.stale is True

    cache.invalidate("alpha")
    empty = cache.lookup("alpha")
    assert empty.present is False


def test_activation_cache_roundtrip() -> None:
    cache = ActivationCache[dict[str, int]]()

    assert cache.get("key") is None
    headers = cache.conditional_headers("key")
    assert "If-None-Match" not in headers

    cache.set("key", "etag-1", {"value": 1})
    entry = cache.get("key")
    assert entry is not None
    assert entry.payload == {"value": 1}

    headers = cache.conditional_headers("key", {"Accept": "application/json"})
    assert headers["If-None-Match"] == "etag-1"
    assert headers["Accept"] == "application/json"

    cache.invalidate("key")
    assert cache.get("key") is None


@pytest.mark.asyncio
async def test_breaker_transport_retries_and_recovers() -> None:
    client = StubAsyncClient(
        [
            httpx.ConnectError("boom"),
            httpx.Response(200, json={"ok": True}),
        ]
    )
    wait_calls: list[tuple[int, Exception]] = []
    latency: list[float] = []
    on_success: list[int] = []

    async def wait_for_service(attempt: int, exc: Exception) -> None:
        wait_calls.append((attempt, exc))

    transport = BreakerRetryTransport(
        cast(httpx.AsyncClient, client),
        AsyncCircuitBreaker(max_failures=2),
        timeout=0.05,
        retries=1,
        wait_for_service=wait_for_service,
        observe_latency=latency.append,
        on_success=lambda breaker: on_success.append(breaker.failures),
    )

    response = await transport.request("GET", "http://example.com")

    assert response.status_code == 200
    assert len(client.calls) == 2
    assert wait_calls and wait_calls[0][0] == 1
    assert latency  # latency observer invoked
    assert on_success == [0]


@pytest.mark.asyncio
async def test_breaker_transport_opens_circuit() -> None:
    events: list[str] = []
    breaker = AsyncCircuitBreaker(max_failures=1, on_open=lambda: events.append("open"))
    client = StubAsyncClient([httpx.ConnectError("boom")])
    transport = BreakerRetryTransport(
        cast(httpx.AsyncClient, client),
        breaker,
        timeout=0.05,
        retries=0,
    )

    with pytest.raises(httpx.ConnectError):
        await transport.request("GET", "http://example.com")

    assert events == ["open"]
    assert breaker.is_open

    with pytest.raises(RuntimeError, match="circuit open"):
        await transport.request("GET", "http://example.com")

    # Second attempt should fail fast without touching the client
    assert len(client.calls) == 1


@pytest.mark.asyncio
async def test_augment_decision_payload_records_downgrade(reset_gateway_metrics) -> None:
    payload = {"effective_mode": "paper"}
    augmented = augment_decision_payload("world-123", payload)

    assert augmented["execution_domain"] == "backtest"
    context = augmented["compute_context"]
    assert context["world_id"] == "world-123"
    assert context["downgraded"] is True
    assert context["downgrade_reason"] == DowngradeReason.MISSING_AS_OF

    metric_value = (
        reset_gateway_metrics.worlds_compute_context_downgrade_total.labels(
            reason=DowngradeReason.MISSING_AS_OF.value
        )._value.get()
    )
    assert metric_value == 1
