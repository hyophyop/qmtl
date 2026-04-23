from datetime import datetime, timedelta, timezone

import pytest

from qmtl.services.worldservice.risk_hub import (
    PortfolioSnapshot,
    RiskSignalHub,
    RiskSnapshotConflictError,
)


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


class _RacingConflictRepo:
    def __init__(self) -> None:
        self.insert_attempted = False

    async def get(self, world_id: str, version: str):
        if not self.insert_attempted:
            return None
        return {
            "world_id": world_id,
            "as_of": "2025-01-01T00:00:00Z",
            "version": version,
            "hash": "other-hash",
            "weights": {"a": 1.0},
        }

    async def upsert(self, world_id: str, payload: dict):
        self.insert_attempted = True
        raise RuntimeError("unique constraint failed")


class _BrokenRepo:
    async def get(self, world_id: str, version: str):
        return None

    async def upsert(self, world_id: str, payload: dict):
        raise RuntimeError("db unavailable")


class _RecordingRepo:
    def __init__(self) -> None:
        self.upsert_calls = 0

    async def get(self, world_id: str, version: str):
        return None

    async def upsert(self, world_id: str, payload: dict):
        self.upsert_calls += 1


@pytest.mark.asyncio
async def test_repository_race_conflict_is_raised_instead_of_silently_acked():
    hub = RiskSignalHub()
    hub.bind_repository(_RacingConflictRepo())
    snap = PortfolioSnapshot(
        world_id="w",
        as_of="2025-01-01T00:00:00Z",
        version="v1",
        weights={"a": 1.0},
    )

    with pytest.raises(RiskSnapshotConflictError):
        await hub.upsert_snapshot(snap)

    assert hub._snapshots == {}


@pytest.mark.asyncio
async def test_repository_failure_is_not_cached_locally_when_persist_fails():
    hub = RiskSignalHub()
    hub.bind_repository(_BrokenRepo())
    snap = PortfolioSnapshot(
        world_id="w",
        as_of="2025-01-01T00:00:00Z",
        version="v1",
        weights={"a": 1.0},
    )

    with pytest.raises(RuntimeError, match="db unavailable"):
        await hub.upsert_snapshot(snap)

    assert hub._snapshots == {}


@pytest.mark.asyncio
async def test_in_memory_conflict_blocks_repository_write_before_persist() -> None:
    hub = RiskSignalHub()
    repo = _RecordingRepo()
    original = PortfolioSnapshot(
        world_id="w",
        as_of="2025-01-01T00:00:00Z",
        version="v1",
        weights={"a": 1.0},
    )
    await hub.upsert_snapshot(original)
    hub.bind_repository(repo)

    conflicting = PortfolioSnapshot(
        world_id="w",
        as_of="2025-01-01T00:00:00Z",
        version="v1",
        weights={"a": 0.9, "b": 0.1},
    )

    with pytest.raises(RiskSnapshotConflictError):
        await hub.upsert_snapshot(conflicting)

    assert repo.upsert_calls == 0


@pytest.mark.asyncio
async def test_pending_dispatch_versions_are_pruned_when_snapshot_cache_evicts_them() -> None:
    hub = RiskSignalHub(max_cached=1)

    first = PortfolioSnapshot(
        world_id="w",
        as_of="2025-01-01T00:00:00Z",
        version="v1",
        weights={"a": 1.0},
    )
    second = PortfolioSnapshot(
        world_id="w",
        as_of="2025-01-01T00:01:00Z",
        version="v2",
        weights={"a": 1.0},
    )

    await hub.upsert_snapshot(first)
    assert hub.snapshot_dispatch_pending("w", "v1") is True

    await hub.upsert_snapshot(second)

    assert hub.snapshot_dispatch_pending("w", "v1") is False
    assert hub.snapshot_dispatch_pending("w", "v2") is True


def test_pending_dispatch_versions_are_pruned_when_deadline_expires() -> None:
    hub = RiskSignalHub()
    hub._pending_dispatches = {  # type: ignore[assignment]
        "w": {"v1": datetime.now(timezone.utc) - timedelta(seconds=1)}
    }

    assert hub.snapshot_dispatch_pending("w", "v1") is False
    assert "w" not in hub._pending_dispatches
