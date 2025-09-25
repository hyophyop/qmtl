from __future__ import annotations

import asyncio
from typing import Optional

import pandas as pd
import pytest

from qmtl.runtime.sdk.seamless_data_provider import (
    SeamlessDataProvider,
    DataSource,
    DataSourcePriority,
    ConformancePipelineError,
)
from qmtl.runtime.io.seamless_provider import (
    StorageDataSource,
    DataFetcherAutoBackfiller,
)
from qmtl.runtime.sdk import metrics as sdk_metrics
from qmtl.runtime.sdk.conformance import ConformancePipeline


class _StaticSource:
    """Simple DataSource with fixed coverage and optional frame generation."""

    def __init__(self, coverage: list[tuple[int, int]], priority: DataSourcePriority) -> None:
        self._coverage = list(coverage)
        self.priority = priority

    async def is_available(self, start: int, end: int, *, node_id: str, interval: int) -> bool:
        for s, e in self._coverage:
            if s <= start and end <= e:
                return True
        return False

    async def fetch(self, start: int, end: int, *, node_id: str, interval: int) -> pd.DataFrame:
        # Return a simple frame with ts only for the requested range (aligned)
        rows = [{"ts": ts} for ts in range(start, end + 1, interval)]
        return pd.DataFrame(rows)

    async def coverage(self, *, node_id: str, interval: int) -> list[tuple[int, int]]:
        return list(self._coverage)

    # Helper to mutate coverage in tests
    def add_range(self, start: int, end: int) -> None:
        self._coverage.append((start, end))


class _DuplicateSource(_StaticSource):
    """Data source that deliberately emits duplicate timestamps."""

    async def fetch(self, start: int, end: int, *, node_id: str, interval: int) -> pd.DataFrame:
        # two identical rows trigger duplicate detection in the conformance pipeline
        return pd.DataFrame([
            {"ts": start},
            {"ts": start},
        ])


class _DummyProvider(SeamlessDataProvider):
    """Concrete instance of SeamlessDataProvider using injected sources/backfiller."""

    pass


@pytest.mark.asyncio
async def test_coverage_merges_adjacent_ranges_interval_aware() -> None:
    # Adjacent ranges at interval=10 should merge
    cache = _StaticSource([(0, 100)], DataSourcePriority.CACHE)
    storage = _StaticSource([(110, 200)], DataSourcePriority.STORAGE)
    provider = _DummyProvider(cache_source=cache, storage_source=storage)

    merged = await provider.coverage(node_id="n", interval=10)
    assert merged == [(0, 200)]


@pytest.mark.asyncio
async def test_seamless_fetch_deduplicates_boundary_bars() -> None:
    cache = _StaticSource([(0, 100)], DataSourcePriority.CACHE)
    storage = _StaticSource([(100, 200)], DataSourcePriority.STORAGE)
    provider = _DummyProvider(cache_source=cache, storage_source=storage)

    df = await provider.fetch(0, 200, node_id="n", interval=10)

    expected = list(range(0, 201, 10))
    assert df["ts"].tolist() == expected


@pytest.mark.asyncio
async def test_seamless_fetch_preserves_off_grid_cache_bounds() -> None:
    cache = _StaticSource([(95, 100)], DataSourcePriority.CACHE)
    storage = _StaticSource([(0, 200)], DataSourcePriority.STORAGE)
    provider = _DummyProvider(cache_source=cache, storage_source=storage)

    df = await provider.fetch(0, 200, node_id="n", interval=10)

    ts = df["ts"].tolist()
    assert 90 in ts  # previously dropped due to misaligned subtraction
    assert ts.count(90) == 1
    assert ts.count(95) == 1


@pytest.mark.asyncio
async def test_find_missing_ranges_uses_interval_math() -> None:
    storage = _StaticSource([(0, 100)], DataSourcePriority.STORAGE)
    provider = _DummyProvider(storage_source=storage)
    # Request [0, 200] at interval=10 → gap is [110, 200]
    available = await provider.coverage(node_id="n", interval=10)
    # Access internal helper via public ensure routine to compute gaps indirectly
    ok = await provider.ensure_data_available(0, 200, node_id="n", interval=10)
    # No backfiller present, so availability remains False
    assert ok is False
    # Validate helper behavior directly
    gaps = provider._find_missing_ranges(0, 200, available, 10)  # type: ignore[attr-defined]
    assert gaps == [(110, 200)]


class _CountingBackfiller:
    """AutoBackfiller-like stub that records calls and updates storage coverage."""

    def __init__(self, storage_source: _StaticSource) -> None:
        self.calls: list[tuple[int, int, str, int]] = []
        self._storage = storage_source

    async def can_backfill(self, start: int, end: int, *, node_id: str, interval: int) -> bool:
        return True

    async def backfill(
        self, start: int, end: int, *, node_id: str, interval: int, target_storage: Optional[DataSource] = None
    ) -> pd.DataFrame:
        self.calls.append((start, end, node_id, interval))
        # Simulate producing data and materializing into storage by mutating coverage
        self._storage.add_range(start, end)
        # Return a small frame indicating success
        return pd.DataFrame([{"ts": start}, {"ts": end}])

    async def backfill_async(self, *args, **kwargs):  # pragma: no cover - not used here
        yield pd.DataFrame()


@pytest.mark.asyncio
async def test_background_backfill_single_flight_dedup() -> None:
    sdk_metrics.reset_metrics()
    storage = _StaticSource([], DataSourcePriority.STORAGE)
    backfiller = _CountingBackfiller(storage)
    provider = _DummyProvider(storage_source=storage, backfiller=backfiller, enable_background_backfill=True)

    async def call_twice():
        # Fire two overlapping requests for the same range
        t1 = asyncio.create_task(provider.ensure_data_available(0, 100, node_id="n", interval=10))
        t2 = asyncio.create_task(provider.ensure_data_available(0, 100, node_id="n", interval=10))
        await asyncio.gather(t1, t2)

    await call_twice()
    # Let background task run to completion
    for _ in range(3):
        await asyncio.sleep(0)
    # Only one backfill should have been scheduled
    assert len(backfiller.calls) == 1
    # Metrics recorded: last ts and jobs back to zero
    key = ("n", "10")
    assert sdk_metrics.backfill_last_timestamp._vals.get(key) == 100  # type: ignore[attr-defined]
    assert sdk_metrics.backfill_jobs_in_progress._val == 0  # type: ignore[attr-defined]


class _FakeFetcher:
    def __init__(self):
        self.calls = 0

    async def fetch(self, start: int, end: int, *, node_id: str, interval: int) -> pd.DataFrame:  # pragma: no cover
        self.calls += 1
        return pd.DataFrame([{"ts": start}])


class _FakeStorageProvider:
    def __init__(self):
        self.filled: list[tuple[int, int, str, int]] = []
        self.fetched: list[tuple[int, int, str, int]] = []

    async def fill_missing(self, start: int, end: int, *, node_id: str, interval: int) -> None:
        self.filled.append((start, end, node_id, interval))

    async def fetch(self, start: int, end: int, *, node_id: str, interval: int) -> pd.DataFrame:
        self.fetched.append((start, end, node_id, interval))
        return pd.DataFrame([{"ts": start}, {"ts": end}])

    async def coverage(self, *, node_id: str, interval: int) -> list[tuple[int, int]]:  # pragma: no cover
        return []


@pytest.mark.asyncio
async def test_storage_backfill_materializes_and_reads_back() -> None:
    sdk_metrics.reset_metrics()
    storage_provider = _FakeStorageProvider()

    class _StorageDS(StorageDataSource):
        # Expose required attribute to satisfy DataFetcherAutoBackfiller contract
        def __init__(self, sp):
            self.storage_provider = sp
            self.priority = DataSourcePriority.STORAGE

        async def is_available(self, *args, **kwargs):  # pragma: no cover
            return False

        async def fetch(self, *args, **kwargs):  # pragma: no cover
            return pd.DataFrame()

        async def coverage(self, *args, **kwargs):  # pragma: no cover
            return []

    storage_ds = _StorageDS(storage_provider)
    fetcher = _FakeFetcher()
    backfiller = DataFetcherAutoBackfiller(fetcher)

    df = await backfiller.backfill(0, 100, node_id="n", interval=10, target_storage=storage_ds)

    # Should use storage.fill_missing then storage.fetch once; never call fetcher
    assert storage_provider.filled == [(0, 100, "n", 10)]
    assert storage_provider.fetched == [(0, 100, "n", 10)]
    assert fetcher.calls == 0
    assert not df.empty and set(df["ts"]) == {0, 100}


@pytest.mark.asyncio
async def test_ensure_data_available_sync_returns_true() -> None:
    sdk_metrics.reset_metrics()
    storage = _StaticSource([], DataSourcePriority.STORAGE)
    backfiller = _CountingBackfiller(storage)
    provider = _DummyProvider(
        storage_source=storage,
        backfiller=backfiller,
        enable_background_backfill=False,  # synchronous path
    )
    ok = await provider.ensure_data_available(0, 100, node_id="n", interval=10)
    assert ok is True
    assert len(backfiller.calls) == 1
    key = ("n", "10")
    assert sdk_metrics.backfill_last_timestamp._vals.get(key) == 100  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_fetch_seamless_records_metrics_on_backfill() -> None:
    sdk_metrics.reset_metrics()
    storage = _StaticSource([], DataSourcePriority.STORAGE)
    backfiller = _CountingBackfiller(storage)
    provider = _DummyProvider(storage_source=storage, backfiller=backfiller)

    df = await provider.fetch(0, 100, node_id="n", interval=10)
    assert isinstance(df, pd.DataFrame)
    key = ("n", "10")
    assert sdk_metrics.backfill_last_timestamp._vals.get(key) == 100  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_conformance_pipeline_blocks_by_default() -> None:
    provider = _DummyProvider(
        storage_source=_DuplicateSource([(0, 10)], DataSourcePriority.STORAGE),
        conformance=ConformancePipeline(),
    )

    with pytest.raises(ConformancePipelineError) as exc:
        await provider.fetch(0, 10, node_id="n", interval=10)

    report = exc.value.report
    assert report.warnings and "duplicate" in report.warnings[0]
    assert "duplicate_bars" in report.flags_counts
    assert provider.last_conformance_report is report


@pytest.mark.asyncio
async def test_conformance_pipeline_respects_partial_ok() -> None:
    provider = _DummyProvider(
        storage_source=_DuplicateSource([(0, 10)], DataSourcePriority.STORAGE),
        conformance=ConformancePipeline(),
        partial_ok=True,
    )

    df = await provider.fetch(0, 10, node_id="n", interval=10)
    assert df["ts"].tolist() == [0]

    report = provider.last_conformance_report
    assert report is not None
    assert report.flags_counts.get("duplicate_bars") == 1
