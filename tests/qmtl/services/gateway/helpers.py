from __future__ import annotations

import base64
import json
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Awaitable, Callable

import httpx

from qmtl.foundation.common import compute_node_id, crc32_of_list
from qmtl.services.gateway.api import Database, create_app
from qmtl.services.gateway.models import StrategySubmit
from qmtl.services.gateway.world_client import WorldServiceClient


Handler = Callable[[httpx.Request], Awaitable[httpx.Response]]


@dataclass(slots=True)
class GatewayTestContext:
    """Container for the components yielded by :func:`gateway_app`."""

    client: httpx.AsyncClient
    world_client: WorldServiceClient
    database: Database


@dataclass(slots=True)
class StubGatewayDatabase(Database):
    """In-memory database implementation for Gateway API tests."""

    events: list[tuple[str, str]] = field(default_factory=list)

    async def insert_strategy(self, strategy_id: str, meta: dict | None) -> None:
        return None

    async def set_status(self, strategy_id: str, status: str) -> None:
        return None

    async def get_status(self, strategy_id: str) -> str | None:
        return None

    async def append_event(self, strategy_id: str, event: str) -> None:
        self.events.append((strategy_id, event))


@dataclass(slots=True)
class _ProducerStub:
    async def stop(self) -> None:  # pragma: no cover - simple stub
        return None


@dataclass(slots=True)
class StubCommitLogWriter:
    """Commit log writer stub capturing published payloads."""

    published: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    submissions: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    _producer: _ProducerStub = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._producer = _ProducerStub()

    async def publish_submission(
        self, strategy_id: str, payload: dict[str, Any], *, timestamp_ms: int | None = None
    ) -> None:
        self.submissions.append((strategy_id, payload))

    async def publish_rebalance_batch(
        self, batch_id: str, payload: dict[str, Any], *, timestamp_ms: int | None = None
    ) -> None:
        self.published.append((batch_id, payload))


@asynccontextmanager
async def gateway_app(
    handler: Handler,
    *,
    redis_client: Any,
    database: Database | None = None,
    base_url: str = "http://test",
    world_url: str = "http://world",
    client_kwargs: dict[str, Any] | None = None,
    world_client_kwargs: dict[str, Any] | None = None,
    create_app_kwargs: dict[str, Any] | None = None,
    transport: httpx.BaseTransport | None = None,
    commit_log_writer: Any | None = None,
) -> AsyncIterator[GatewayTestContext]:
    """Spin up a Gateway ASGI app wired to a mocked WorldService client."""

    db = database or StubGatewayDatabase()
    transport = transport or httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport)
    world_client = WorldServiceClient(
        world_url,
        client=http_client,
        **(world_client_kwargs or {}),
    )
    kwargs = {
        "redis_client": redis_client,
        "database": db,
        "world_client": world_client,
        "enable_background": False,
    }
    if commit_log_writer is not None:
        kwargs["commit_log_writer"] = commit_log_writer
    if create_app_kwargs:
        kwargs.update(create_app_kwargs)

    app = create_app(**kwargs)

    try:
        async with httpx.ASGITransport(app=app) as asgi:
            params = {"transport": asgi, "base_url": base_url}
            if client_kwargs:
                params.update(client_kwargs)
            async with httpx.AsyncClient(**params) as api_client:
                yield GatewayTestContext(
                    client=api_client,
                    world_client=world_client,
                    database=db,
                )
    finally:
        await world_client._client.aclose()


def make_jwt(payload: dict[str, Any]) -> str:
    """Return an unsigned JWT token for identity propagation tests."""

    header = base64.urlsafe_b64encode(
        json.dumps({"alg": "none", "typ": "JWT"}).encode()
    ).decode().rstrip("=")
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    return f"{header}.{body}."


@dataclass(slots=True)
class StrategyPayloadBundle:
    """Bundle of artefacts used by strategy submission tests."""

    payload: StrategySubmit
    dag: dict[str, Any]
    expected_node_id: str


def build_strategy_payload(
    *,
    mismatch: bool = False,
    execution_domain: str | None = " sim ",
    include_as_of: bool = True,
    as_of_value: str = "2025-01-01T00:00:00Z",
) -> StrategyPayloadBundle:
    """Construct a strategy submission payload with optional variations."""

    base_node = {
        "node_type": "TagQueryNode",
        "code_hash": "code",
        "config_hash": "config",
        "schema_hash": "schema",
        "schema_compat_id": "schema-compat",
        "params": {"tags": ["alpha"], "match_mode": "any"},
        "dependencies": [],
        "tags": ["alpha"],
        "interval": 5,
        "match_mode": "any",
    }
    expected_node_id = compute_node_id(base_node)
    node_id = "bad-node" if mismatch else expected_node_id
    dag = {
        "nodes": [
            {
                "node_id": node_id,
                **base_node,
            }
        ]
    }
    dag_json = base64.b64encode(json.dumps(dag).encode()).decode()
    node_crc = crc32_of_list([node_id])

    meta: dict[str, Any] = {}
    if execution_domain is not None:
        meta["execution_domain"] = execution_domain
    if include_as_of:
        meta["as_of"] = as_of_value

    payload = StrategySubmit(
        dag_json=dag_json,
        meta=meta or None,
        world_id="world-1",
        node_ids_crc32=node_crc,
    )

    return StrategyPayloadBundle(
        payload=payload,
        dag=dag,
        expected_node_id=expected_node_id,
    )
