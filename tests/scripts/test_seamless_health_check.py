from __future__ import annotations

from typing import Any

import pytest

from scripts import seamless_health_check as health


class _DummyResponse:
    def __init__(self, status_code: int, payload: Any = None) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> Any:
        if self._payload is None:
            raise ValueError("no payload")
        return self._payload


def test_verify_required_env_passes_when_all_present() -> None:
    env = {"QMTL_SEAMLESS_COORDINATOR_URL": "https://coordinator"}
    result = health.verify_required_env(["QMTL_SEAMLESS_COORDINATOR_URL"], environ=env)
    assert result.success


def test_verify_required_env_fails_when_missing() -> None:
    result = health.verify_required_env(["QMTL_SEAMLESS_COORDINATOR_URL"], environ={})
    assert not result.success
    assert "Missing values" in result.message


def test_check_coordinator_health_reports_status_from_payload() -> None:
    def fake_get(url: str, params: dict[str, str] | None, timeout: float) -> _DummyResponse:
        assert url == "https://coordinator/health"
        return _DummyResponse(200, {"status": "ok"})

    result = health.check_coordinator_health(
        "https://coordinator",
        http_get=fake_get,
    )
    assert result.success


@pytest.mark.parametrize(
    "status_payload",
    [
        {"status": "fail"},
        {"state": "degraded"},
    ],
)
def test_check_coordinator_health_flags_unhealthy_status(status_payload: dict[str, str]) -> None:
    def fake_get(url: str, params: dict[str, str] | None, timeout: float) -> _DummyResponse:
        return _DummyResponse(200, status_payload)

    result = health.check_coordinator_health(
        "https://coordinator",
        http_get=fake_get,
    )
    assert not result.success


def test_check_prometheus_metrics_detects_missing_series() -> None:
    responses = {
        "backfill_completion_ratio": _DummyResponse(200, {"status": "success", "data": [{}]}),
        "seamless_sla_deadline_seconds": _DummyResponse(200, {"status": "success", "data": []}),
    }

    def fake_get(url: str, params: dict[str, str] | None, timeout: float) -> _DummyResponse:
        assert params is not None
        metric = params["match[]"]
        return responses[metric]

    result = health.check_prometheus_metrics(
        "https://prometheus:9090",
        ["backfill_completion_ratio", "seamless_sla_deadline_seconds"],
        http_get=fake_get,
    )
    assert not result.success
    assert "Missing series" in result.message


def test_check_prometheus_metrics_succeeds_with_active_series() -> None:
    def fake_get(url: str, params: dict[str, str] | None, timeout: float) -> _DummyResponse:
        return _DummyResponse(200, {"status": "success", "data": [{"__name__": params["match[]"]}]})

    result = health.check_prometheus_metrics(
        "https://prometheus:9090",
        ["backfill_completion_ratio"],
        http_get=fake_get,
    )
    assert result.success
