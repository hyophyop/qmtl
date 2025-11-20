from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Callable, cast

import httpx
import pytest

from qmtl.services.gateway import metrics

from tests.qmtl.services.gateway.helpers import (
    GatewayTestContext,
    Handler,
    StubGatewayDatabase,
    gateway_app,
)
from tests.qmtl.services.gateway.fixtures import (
    DB_BUILDERS,
    DummyDagManager,
    DummyDatabase,
    DummyManager,
    StubWorldClient,
)


@pytest.fixture
def gateway_stub_db() -> StubGatewayDatabase:
    """Provide a fresh stub database for Gateway API tests."""

    return StubGatewayDatabase()


@pytest.fixture
def mock_world_service() -> Callable[[Handler], httpx.MockTransport]:
    """Return a factory that produces httpx.MockTransport instances."""

    def factory(handler: Handler) -> httpx.MockTransport:
        return httpx.MockTransport(handler)

    return factory


@pytest.fixture
def gateway_app_factory(
    fake_redis, gateway_stub_db, mock_world_service
) -> Callable[..., AsyncIterator[GatewayTestContext]]:
    """Return an async factory for exercising the Gateway ASGI app."""

    def factory(
        handler: Handler,
        *,
        redis_client: Any | None = None,
        database: StubGatewayDatabase | None = None,
        app_kwargs: dict[str, Any] | None = None,
        client_kwargs: dict[str, Any] | None = None,
        world_client_kwargs: dict[str, Any] | None = None,
        commit_log_writer: Any | None = None,
    ) -> AsyncIterator[GatewayTestContext]:
        transport = mock_world_service(handler)
        return cast(
            AsyncIterator[GatewayTestContext],
            gateway_app(
                handler,
                redis_client=redis_client or fake_redis,
                database=database or gateway_stub_db,
                client_kwargs=client_kwargs,
                world_client_kwargs=world_client_kwargs,
                create_app_kwargs=app_kwargs,
                transport=transport,
                commit_log_writer=commit_log_writer,
            ),
        )

    return factory


@pytest.fixture
def asgi_client_factory():
    """Yield an async HTTPX client bound to an ASGI app under test."""

    @asynccontextmanager
    async def factory(
        app,
        *,
        base_url: str = "http://test",
        client_kwargs: dict[str, Any] | None = None,
    ) -> AsyncIterator[httpx.AsyncClient]:
        async with httpx.ASGITransport(app=app) as asgi:
            async with httpx.AsyncClient(
                transport=asgi,
                base_url=base_url,
                **(client_kwargs or {}),
            ) as api_client:
                yield api_client

    return factory


@pytest.fixture
def reset_gateway_metrics():
    """Reset Gateway metrics before and after a test run."""

    metrics.reset_metrics()
    try:
        yield metrics
    finally:
        metrics.reset_metrics()


@pytest.fixture
def dummy_manager() -> DummyManager:
    """Return a fresh :class:`DummyManager` instance."""

    return DummyManager()


@pytest.fixture
def dummy_dag_manager() -> DummyDagManager:
    """Return a fresh :class:`DummyDagManager` instance."""

    return DummyDagManager()


@pytest.fixture
def dummy_database() -> DummyDatabase:
    """Return a fresh :class:`DummyDatabase` instance."""

    return DummyDatabase()


@pytest.fixture
def stub_world_client_factory() -> Callable[..., StubWorldClient]:
    """Factory fixture for :class:`StubWorldClient` instances."""

    def factory(**kwargs: Any) -> StubWorldClient:
        return StubWorldClient(**kwargs)

    return factory


@pytest.fixture(params=tuple(DB_BUILDERS.keys()), ids=tuple(DB_BUILDERS.keys()))
def world_binding_db_builder(request) -> Callable[..., Any]:
    """Parameterized fixture yielding database builder coroutines."""

    return DB_BUILDERS[request.param]
