from __future__ import annotations

import pytest

from qmtl.foundation.common.compute_context import DowngradeReason
from qmtl.services.gateway.submission.context_service import ComputeContextService
from qmtl.services.gateway.world_client import Budget, WorldServiceClient
from tests.qmtl.services.gateway.helpers import build_strategy_payload

pytestmark = pytest.mark.contract


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
