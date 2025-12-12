import pytest

from qmtl.services.gateway.routes.rebalancing import (
    _build_snapshot_weights,
    _publish_risk_snapshots,
)
from qmtl.services.worldservice.schemas import (
    MultiWorldRebalanceRequest,
    PositionSliceModel,
)


class _StubRiskHubClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def publish_snapshot(self, world_id: str, payload: dict) -> dict:
        self.calls.append((world_id, payload))
        return payload


@pytest.mark.asyncio
async def test_publish_risk_snapshots_uses_strategy_allocations():
    payload = MultiWorldRebalanceRequest(
        total_equity=100.0,
        world_alloc_before={"w": 0.5},
        world_alloc_after={"w": 0.6},
        positions=[
            PositionSliceModel(
                world_id="w",
                symbol="BTC",
                qty=1.0,
                mark=60.0,
                strategy_id="s1",
            )
        ],
        strategy_alloc_before_total={"w": {"s1": 0.5}},
        strategy_alloc_after_total={"w": {"s1": 0.6}},
        min_trade_notional=None,
        lot_size_by_symbol=None,
        mode="scaling",
    )

    weights = _build_snapshot_weights(payload)
    assert weights["w"]["s1"] == pytest.approx(1.0)

    client = _StubRiskHubClient()
    published = await _publish_risk_snapshots(
        client,
        payload,
        schema_version=1,
        as_of="2025-01-01T00:00:00Z",
    )

    assert published is True
    assert client.calls
    world_id, snapshot = client.calls[0]
    assert world_id == "w"
    assert snapshot["weights"]["s1"] == pytest.approx(1.0)
    assert snapshot["as_of"] == "2025-01-01T00:00:00Z"
