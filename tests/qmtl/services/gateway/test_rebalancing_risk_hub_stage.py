import asyncio

import pytest

from qmtl.services.gateway.routes.rebalancing import _publish_risk_snapshots
from qmtl.services.worldservice.schemas import MultiWorldRebalanceRequest, PositionSliceModel


class _StubRiskHubClient:
    def __init__(self):
        self.stage = None
        self.published: list[tuple[str, dict]] = []

    async def publish_snapshot(self, world_id, payload):
        self.published.append((world_id, payload))
        return {}


@pytest.mark.asyncio
async def test_publish_risk_snapshots_carries_stage_into_provenance_and_header():
    client = _StubRiskHubClient()
    payload = MultiWorldRebalanceRequest(
        total_equity=100.0,
        world_alloc_before={"w": 1.0},
        world_alloc_after={"w": 1.0},
        positions=[
            PositionSliceModel(
                world_id="w",
                symbol="BTC",
                qty=1.0,
                mark=100.0,
                strategy_id="s1",
                venue="spot",
            )
        ],
    )

    sent = await _publish_risk_snapshots(
        client,
        payload,
        schema_version=1,
        as_of="2025-01-01T00:00:00Z",
        stage="live",
    )

    assert sent is True
    assert client.stage == "live"
    assert client.published
    wid, snap = client.published[0]
    assert wid == "w"
    assert snap["provenance"]["stage"] == "live"
