import pytest

from qmtl.services.worldservice.risk_hub import RiskSignalHub, PortfolioSnapshot, RiskSnapshotConflictError


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
    with pytest.raises(ValueError, match="expired"):
        await hub.upsert_snapshot(snap)


@pytest.mark.asyncio
async def test_snapshot_version_conflict_is_rejected():
    hub = RiskSignalHub()
    snap = PortfolioSnapshot(
        world_id="w",
        as_of="2025-01-01T00:00:00Z",
        version="v1",
        weights={"a": 1.0},
    )
    await hub.upsert_snapshot(snap)
    conflicting = PortfolioSnapshot(
        world_id="w",
        as_of="2025-01-01T00:00:00Z",
        version="v1",
        weights={"a": 0.9, "b": 0.1},
    )
    with pytest.raises(RiskSnapshotConflictError):
        await hub.upsert_snapshot(conflicting)


@pytest.mark.asyncio
async def test_snapshot_version_idempotent_retry_returns_deduped_true():
    hub = RiskSignalHub()
    snap = PortfolioSnapshot(
        world_id="w",
        as_of="2025-01-01T00:00:00Z",
        version="v1",
        weights={"a": 1.0},
    )
    deduped = await hub.upsert_snapshot(snap)
    assert deduped is False
    retry = PortfolioSnapshot(
        world_id="w",
        as_of="2025-01-01T00:00:00Z",
        version="v1",
        weights={"a": 1.0},
    )
    deduped_retry = await hub.upsert_snapshot(retry)
    assert deduped_retry is True


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
