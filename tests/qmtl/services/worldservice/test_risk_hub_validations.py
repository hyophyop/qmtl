import pytest

from qmtl.services.worldservice.risk_hub import RiskSignalHub, PortfolioSnapshot


@pytest.mark.asyncio
async def test_weight_validation_fails_when_not_normalized():
    hub = RiskSignalHub()
    snap = PortfolioSnapshot(
        world_id="w",
        as_of="2025-01-01T00:00:00Z",
        version="v1",
        weights={"a": 0.7, "b": 0.2},
    )
    with pytest.raises(ValueError):
        await hub.upsert_snapshot(snap)


@pytest.mark.asyncio
async def test_ttl_filters_expired_snapshot():
    hub = RiskSignalHub()
    snap = PortfolioSnapshot(
        world_id="w",
        as_of="2025-01-01T00:00:00Z",
        version="v1",
        weights={"a": 1.0},
        ttl_sec=1,
        created_at="2025-01-01T00:00:00Z",
    )
    await hub.upsert_snapshot(snap)
    latest = await hub.latest_snapshot("w")
    assert latest is None


def test_snapshot_round_trip_preserves_inline_realized_returns():
    payload = {
        "world_id": "w",
        "as_of": "2025-01-01T00:00:00Z",
        "version": "v1",
        "weights": {"s1": 1.0},
        "realized_returns": {"s1": [0.01, -0.005]},
    }
    snapshot = PortfolioSnapshot.from_payload(payload)
    encoded = snapshot.to_dict()
    assert encoded.get("realized_returns") == payload["realized_returns"]
