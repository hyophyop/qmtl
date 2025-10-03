from __future__ import annotations

import pytest
from prometheus_client import CollectorRegistry

from qmtl.foundation.common.health import probe_http, probe_http_async


class DummyResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


def test_probe_http_success_records_metrics() -> None:
    registry = CollectorRegistry()
    calls: list[tuple[str, str]] = []

    def fake_request(method: str, url: str, **_: object) -> DummyResponse:
        calls.append((method, url))
        return DummyResponse(200)

    result = probe_http(
        "https://service/health",
        service="gateway",
        endpoint="/health",
        request=fake_request,
        metrics_registry=registry,
    )

    assert result.ok is True
    assert result.code == "OK"
    assert result.status == 200
    assert result.err is None
    assert result.latency_ms is not None
    assert calls == [("GET", "https://service/health")]

    counter_value = registry.get_sample_value(
        "probe_requests_total",
        {"service": "gateway", "endpoint": "/health", "method": "GET", "result": "OK"},
    )
    assert counter_value == 1.0

    histogram_count = registry.get_sample_value(
        "probe_latency_seconds_count",
        {"service": "gateway", "endpoint": "/health", "method": "GET"},
    )
    assert histogram_count == 1.0

    last_ok = registry.get_sample_value(
        "probe_last_ok_timestamp", {"service": "gateway", "endpoint": "/health"}
    )
    assert last_ok is not None


def test_probe_http_client_error_classification() -> None:
    registry = CollectorRegistry()

    def fake_request(method: str, url: str, **_: object) -> DummyResponse:
        assert method == "HEAD"
        assert url.endswith("/health")
        return DummyResponse(404)

    result = probe_http(
        "https://service/health",
        method="HEAD",
        service="gateway",
        endpoint="/health",
        request=fake_request,
        metrics_registry=registry,
    )

    assert result.ok is False
    assert result.code == "CLIENT_ERROR"
    assert result.status == 404
    assert result.err is None

    counter_value = registry.get_sample_value(
        "probe_requests_total",
        {"service": "gateway", "endpoint": "/health", "method": "HEAD", "result": "CLIENT_ERROR"},
    )
    assert counter_value == 1.0

    last_ok = registry.get_sample_value(
        "probe_last_ok_timestamp", {"service": "gateway", "endpoint": "/health"}
    )
    assert last_ok is None


def test_probe_http_timeout_sets_error_and_metrics() -> None:
    registry = CollectorRegistry()

    def fake_request(*_: object, **__: object) -> DummyResponse:
        raise TimeoutError("probe timed out")

    result = probe_http(
        "https://service/health",
        service="gateway",
        endpoint="/health",
        request=fake_request,
        metrics_registry=registry,
    )

    assert result.ok is False
    assert result.code == "TIMEOUT"
    assert result.status is None
    assert result.err == "probe timed out"

    counter_value = registry.get_sample_value(
        "probe_requests_total",
        {"service": "gateway", "endpoint": "/health", "method": "GET", "result": "TIMEOUT"},
    )
    assert counter_value == 1.0

    last_ok = registry.get_sample_value(
        "probe_last_ok_timestamp", {"service": "gateway", "endpoint": "/health"}
    )
    assert last_ok is None


@pytest.mark.asyncio
async def test_probe_http_async_network_error() -> None:
    registry = CollectorRegistry()

    async def fake_request(*_: object, **__: object) -> None:
        raise ConnectionError("connection dropped")

    result = await probe_http_async(
        "https://service/health",
        service="gateway",
        endpoint="/health",
        request=fake_request,
        metrics_registry=registry,
    )

    assert result.ok is False
    assert result.code == "NETWORK"
    assert result.status is None
    assert result.err == "connection dropped"
