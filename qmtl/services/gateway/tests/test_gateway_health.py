from __future__ import annotations

import asyncio

import pytest

from qmtl.services.gateway import gateway_health as gh_module
from qmtl.services.gateway.gateway_health import (
    GatewayHealthCapabilities,
    get_health,
)


@pytest.fixture(autouse=True)
def clear_gateway_health_cache():
    gh_module._STATUS_CACHE_MAP.clear()  # type: ignore[attr-defined]
    gh_module._STATUS_CACHE_TS = 0.0  # type: ignore[attr-defined]
    yield
    gh_module._STATUS_CACHE_MAP.clear()  # type: ignore[attr-defined]
    gh_module._STATUS_CACHE_TS = 0.0  # type: ignore[attr-defined]


class StubBreaker:
    def __init__(self, open_state: bool = False) -> None:
        self.is_open = open_state


class StubWorldClient:
    def __init__(self, open_state: bool = False) -> None:
        self.breaker = StubBreaker(open_state)


class StubRedis:
    def __init__(self) -> None:
        self.calls = 0

    async def ping(self) -> bool:
        self.calls += 1
        return True


class StubDatabase:
    def __init__(self, *, delay: float = 0.0, result: bool = True) -> None:
        self.calls = 0
        self._delay = delay
        self._result = result

    async def healthy(self) -> bool:
        self.calls += 1
        if self._delay:
            await asyncio.sleep(self._delay)
        return self._result


class StubDagClient:
    def __init__(self, result: bool = True) -> None:
        self.calls = 0
        self._result = result

    async def status(self) -> bool:
        self.calls += 1
        return self._result


@pytest.mark.asyncio
async def test_get_health_returns_capabilities_payload():
    redis = StubRedis()
    database = StubDatabase()
    dag = StubDagClient()
    world = StubWorldClient(open_state=False)
    caps = GatewayHealthCapabilities(
        rebalance_schema_version=2,
        alpha_metrics_capable=True,
        compute_context_contract="compute:v1",
    )

    snapshot = await get_health(
        redis,
        database,
        dag,
        world,
        capabilities=caps,
    )

    assert snapshot["status"] == "ok"
    assert snapshot["worldservice"] == "ok"
    assert snapshot["capabilities"] == {
        "rebalance_schema_version": 2,
        "alpha_metrics_capable": True,
        "compute_context_contract": "compute:v1",
    }


@pytest.mark.asyncio
async def test_get_health_uses_cache_until_ttl_expires():
    redis = StubRedis()
    database = StubDatabase()
    dag = StubDagClient()
    world = StubWorldClient(open_state=False)

    first = await get_health(redis, database, dag, world)
    second = await get_health(redis, database, dag, world)

    assert first is second
    assert redis.calls == 1
    assert database.calls == 1
    assert dag.calls == 1


@pytest.mark.asyncio
async def test_get_health_marks_timeouts_as_degraded():
    redis = StubRedis()
    database = StubDatabase(delay=0.05)
    dag = StubDagClient()
    world = StubWorldClient(open_state=False)

    snapshot = await get_health(
        redis,
        database,
        dag,
        world,
        timeout=0.01,
    )

    assert snapshot["postgres"] == "timeout"
    assert snapshot["status"] == "degraded"
