from __future__ import annotations

import types

import pytest

from qmtl.foundation.common.compute_context import DowngradeReason
from qmtl.services.gateway.submission.context_service import ComputeContextService


class DummyWorldClient:
    def __init__(self, payload, stale: bool = False):
        self.payload = payload
        self.stale = stale
        self.calls: list[str] = []

    async def get_decide(self, world_id: str):
        self.calls.append(world_id)
        return self.payload, self.stale


@pytest.mark.asyncio
async def test_world_decision_overrides_submission_hints() -> None:
    decision = {
        "world_id": "world-1",
        "policy_version": 1,
        "effective_mode": "live",
        "reason": "policy_evaluated",
        "as_of": "2025-01-01T00:00:00Z",
        "ttl": "300s",
        "etag": "etag-1",
    }
    client = DummyWorldClient(decision)
    payload = types.SimpleNamespace(meta={"execution_domain": "shadow"}, world_ids=["world-1"])

    ctx = await ComputeContextService(world_client=client).build(payload)

    assert ctx.execution_domain == "live"  # WS decision wins
    assert ctx.downgraded is False
    assert client.calls == ["world-1"]


@pytest.mark.asyncio
async def test_missing_world_decision_downgrades_to_safe_mode() -> None:
    client = DummyWorldClient(payload=None, stale=False)
    payload = types.SimpleNamespace(meta=None, world_ids=["world-missing"])

    ctx = await ComputeContextService(world_client=client).build(payload)

    assert ctx.execution_domain == "backtest"
    assert ctx.safe_mode is True
    assert ctx.downgraded is True
    assert ctx.downgrade_reason == DowngradeReason.DECISION_UNAVAILABLE
