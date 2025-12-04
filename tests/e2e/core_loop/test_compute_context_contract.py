from __future__ import annotations

import pytest

from qmtl.foundation.common.compute_context import DowngradeReason
from qmtl.services.gateway.submission.context_service import ComputeContextService
from qmtl.services.gateway.world_client import Budget, WorldServiceClient
from tests.qmtl.services.gateway.helpers import build_strategy_payload

pytestmark = pytest.mark.contract


class _StubWorldClient:
    def __init__(self, payload: dict, *, stale: bool = False):
        self._payload = payload
        self._stale = stale

    async def get_decide(self, world_id: str):
        return self._payload, self._stale


@pytest.mark.asyncio
async def test_compute_context_prefers_worldservice_decision(core_loop_stack, core_loop_world_id: str):
    client = WorldServiceClient(
        core_loop_stack.worlds_url,
        budget=Budget(timeout=1.0, retries=0),
    )
    service = ComputeContextService(world_client=client)
    bundle = build_strategy_payload(execution_domain="live", include_as_of=False)
    payload = bundle.payload
    payload.world_ids = [core_loop_world_id]

    try:
        ctx = await service.build(payload)
    finally:
        await client._client.aclose()

    assert ctx.worlds == (core_loop_world_id,)
    assert ctx.execution_domain == "backtest"  # derived from WS decision
    assert ctx.downgraded is False
    assert ctx.safe_mode is False
    assert ctx.as_of


@pytest.mark.asyncio
async def test_compute_context_downgrades_when_world_missing(core_loop_stack):
    client = WorldServiceClient(
        "http://127.0.0.1:1",
        budget=Budget(timeout=0.1, retries=0),
    )
    service = ComputeContextService(world_client=client)
    bundle = build_strategy_payload(execution_domain="live", include_as_of=False)
    payload = bundle.payload
    payload.world_ids = ["missing-world"]

    try:
        ctx = await service.build(payload)
    finally:
        await client._client.aclose()

    assert ctx.worlds == ("missing-world",)
    assert ctx.execution_domain == "backtest"
    assert ctx.safe_mode is True
    assert ctx.downgraded is True
    assert ctx.downgrade_reason == DowngradeReason.DECISION_UNAVAILABLE


@pytest.mark.asyncio
async def test_compute_context_retains_client_as_of_when_ws_lacks_value():
    world_id = "demo-world"
    client = _StubWorldClient({"world_id": world_id, "effective_mode": "validate"})
    service = ComputeContextService(world_client=client)
    bundle = build_strategy_payload(execution_domain="live", include_as_of=True, as_of_value="2025-01-01T00:00:00Z")
    payload = bundle.payload
    payload.world_ids = [world_id]

    ctx = await service.build(payload)

    assert ctx.worlds == (world_id,)
    assert ctx.as_of == "2025-01-01T00:00:00Z"
    assert ctx.execution_domain == "backtest"  # WS context is authoritative
    assert ctx.safe_mode is False
    assert ctx.downgraded is False


@pytest.mark.asyncio
async def test_compute_context_downgrades_on_stale_decision():
    world_id = "demo-world"
    client = _StubWorldClient(
        {"world_id": world_id, "effective_mode": "live", "as_of": "2025-01-01T00:00:00Z"},
        stale=True,
    )
    service = ComputeContextService(world_client=client)
    bundle = build_strategy_payload(execution_domain="live", include_as_of=False)
    payload = bundle.payload
    payload.world_ids = [world_id]

    ctx = await service.build(payload)

    assert ctx.worlds == (world_id,)
    assert ctx.execution_domain == "backtest"
    assert ctx.safe_mode is True
    assert ctx.downgraded is True
    assert ctx.downgrade_reason == DowngradeReason.STALE_DECISION
