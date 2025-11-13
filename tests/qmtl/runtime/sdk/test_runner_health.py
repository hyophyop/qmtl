from __future__ import annotations

import pytest

from qmtl.runtime.sdk import runner
from qmtl.runtime.sdk import runtime as sdk_runtime


@pytest.mark.asyncio
async def test_runner_refreshes_gateway_health(monkeypatch) -> None:
    async def fake_health(*, gateway_url: str, headers: dict[str, str] | None = None) -> dict[str, object]:
        return {"rebalance_schema_version": 2, "alpha_metrics_capable": True}

    client = runner.Runner.services().gateway_client
    monkeypatch.setattr(client, "get_health", fake_health)

    await runner.Runner._refresh_gateway_capabilities("http://gw")

    assert sdk_runtime.REBALANCE_SCHEMA_VERSION == 2
    assert sdk_runtime.ALPHA_METRICS_CAPABLE is True

    sdk_runtime.set_gateway_capabilities(rebalance_schema_version=1, alpha_metrics_capable=False)
