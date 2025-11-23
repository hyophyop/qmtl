import secrets
from typing import Any

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient

from qmtl.services.gateway import api
from qmtl.services.gateway.degradation import DegradationLevel
from qmtl.services.gateway.gateway_health import GatewayHealthCapabilities


class _FakeRedis:
    def __init__(self) -> None:
        self.connection_pool = self

    async def aclose(self) -> None:  # pragma: no cover - exercised via lifespan
        return

    async def close(self) -> None:  # pragma: no cover - exercised via lifespan
        return

    async def disconnect(self) -> None:  # pragma: no cover - exercised via lifespan
        return


class _FakeDagManager:
    async def close(self) -> None:  # pragma: no cover - exercised via lifespan
        return


class _FakeStrategyManager:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        return


class _FakeComputeContext:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        return


class _FakeSubmissionPipeline:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        return


@pytest.fixture()
def patched_app(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    def fake_router(*_: Any, **__: Any) -> APIRouter:
        router = APIRouter()

        @router.get("/ping")
        async def _ping() -> dict[str, str]:
            return {"status": "ok"}

        return router

    def fake_event_router(*_: Any, **__: Any) -> APIRouter:
        router = APIRouter()

        @router.get("/events")
        async def _events() -> dict[str, str]:
            return {"events": "ok"}

        return router

    monkeypatch.setattr(api, "create_api_router", fake_router)
    monkeypatch.setattr(api, "create_event_router", fake_event_router)
    monkeypatch.setattr(api, "StrategyManager", _FakeStrategyManager)
    monkeypatch.setattr(api, "DagManagerClient", lambda *a, **k: _FakeDagManager())
    monkeypatch.setattr(api, "ComputeContextService", _FakeComputeContext)
    monkeypatch.setattr(api, "SubmissionPipeline", _FakeSubmissionPipeline)

    redis_client = _FakeRedis()
    database = api.MemoryDatabase()
    app = api.create_app(
        redis_client=redis_client,
        database=database,
        enable_background=False,
    )
    return TestClient(app)


def test_invalid_database_backend_raises_value_error() -> None:
    with pytest.raises(ValueError):
        api._resolve_database(None, "unknown", None)


def test_world_client_capabilities_are_configured() -> None:
    class DummyWorldClient:
        def __init__(self) -> None:
            self.calls: list[tuple[int, bool]] = []

        def configure_rebalance_capabilities(
            self, *, schema_version: int, alpha_metrics_capable: bool
        ) -> None:
            self.calls.append((schema_version, alpha_metrics_capable))

    client = DummyWorldClient()
    caps = GatewayHealthCapabilities(rebalance_schema_version=2, alpha_metrics_capable=True)

    result = api._resolve_world_client(
        client, enable_proxy=False, url=None, timeout=0.1, retries=1, capabilities=caps
    )

    assert result is client
    assert client.calls == [(2, True)]


def test_world_client_proxy_disabled_without_url() -> None:
    caps = GatewayHealthCapabilities(rebalance_schema_version=1, alpha_metrics_capable=False)
    result = api._resolve_world_client(
        None, enable_proxy=True, url=None, timeout=0.1, retries=1, capabilities=caps
    )
    assert result is None


def test_event_config_generates_secret_and_warns(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    monkeypatch.setattr(secrets, "token_hex", lambda n: "x" * (n * 2))
    caplog.set_level("WARNING")

    config = api._resolve_event_config(None)

    assert config.active_kid == "default"
    assert config.keys["default"] == "x" * 64
    assert any("Gateway events.secret not configured" in msg for msg in caplog.messages)


def test_degrade_middleware_handles_minimal_and_static(patched_app: TestClient) -> None:
    patched_app.app.state.degradation.level = DegradationLevel.STATIC
    response = patched_app.post("/strategies")
    assert response.status_code == 204
    assert response.headers.get("Retry-After") == "30"

    patched_app.app.state.degradation.level = DegradationLevel.MINIMAL
    response = patched_app.post("/strategies")
    assert response.status_code == 503
