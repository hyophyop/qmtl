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
from qmtl.runtime.sdk import seamless_data_provider as seamless_module
from qmtl.runtime.sdk.sla import SLAPolicy
from qmtl.runtime.sdk.exceptions import SeamlessSLAExceeded
from qmtl.runtime.sdk.backfill_coordinator import Lease


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


class _FakeClock:
    def __init__(self) -> None:
        self._value = 0.0

    def monotonic(self) -> float:
        return self._value

    def advance(self, seconds: float) -> None:
        self._value += seconds


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


class _RecordingBackfiller:
    """Minimal backfiller capturing invocations for background tests."""

    def __init__(self) -> None:
        self.calls: list[tuple[int, int, str, int]] = []

    async def can_backfill(self, start: int, end: int, *, node_id: str, interval: int) -> bool:
        return True

    async def backfill(
        self,
        start: int,
        end: int,
        *,
        node_id: str,
        interval: int,
        target_storage: Optional[DataSource] = None,
    ) -> pd.DataFrame:
        self.calls.append((start, end, node_id, interval))
        return pd.DataFrame([{"ts": start}, {"ts": end}])

    async def backfill_async(self, *args, **kwargs):  # pragma: no cover - not used
        yield pd.DataFrame()


class _FailingBackfiller(_RecordingBackfiller):
    """Backfiller that raises to exercise failure instrumentation."""

    def __init__(self, *, exc: Exception | None = None) -> None:
        super().__init__()
        self._exc = exc or RuntimeError("boom")

    async def backfill(
        self,
        start: int,
        end: int,
        *,
        node_id: str,
        interval: int,
        target_storage: Optional[DataSource] = None,
    ) -> pd.DataFrame:
        await super().backfill(start, end, node_id=node_id, interval=interval, target_storage=target_storage)
        raise self._exc


class _FlakyCoordinator:
    def __init__(self, *, raise_on_claim: bool = False, raise_on_complete: bool = False) -> None:
        self.raise_on_claim = raise_on_claim
        self.raise_on_complete = raise_on_complete
        self.claim_calls = 0
        self.complete_calls = 0

    async def claim(self, key: str, lease_ms: int):
        self.claim_calls += 1
        if self.raise_on_claim:
            raise RuntimeError("coordinator unavailable")
        return Lease(key=key, token="lease", lease_until_ms=lease_ms)

    async def complete(self, lease):
        self.complete_calls += 1
        if self.raise_on_complete:
            raise RuntimeError("lease lost")

    async def fail(self, lease, reason: str):  # pragma: no cover - unused
        self.complete_calls += 1


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


@pytest.mark.asyncio
async def test_background_backfill_recovers_from_coordinator_claim_failure() -> None:
    sdk_metrics.reset_metrics()
    backfiller = _RecordingBackfiller()
    coordinator = _FlakyCoordinator(raise_on_claim=True)
    provider = _DummyProvider(
        storage_source=_StaticSource([], DataSourcePriority.STORAGE),
        backfiller=backfiller,
        coordinator=coordinator,
    )

    await provider._start_background_backfill(0, 50, node_id="node", interval=5)
    for _ in range(4):
        await asyncio.sleep(0)

    assert backfiller.calls == [(0, 50, "node", 5)]
    assert provider._active_backfills == {}
    assert coordinator.claim_calls == 1
    assert sdk_metrics.backfill_jobs_in_progress._val == 0  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_background_backfill_handles_lease_completion_errors() -> None:
    sdk_metrics.reset_metrics()
    backfiller = _RecordingBackfiller()
    coordinator = _FlakyCoordinator(raise_on_complete=True)
    provider = _DummyProvider(
        storage_source=_StaticSource([], DataSourcePriority.STORAGE),
        backfiller=backfiller,
        coordinator=coordinator,
    )

    await provider._start_background_backfill(0, 10, node_id="node", interval=5)
    for _ in range(4):
        await asyncio.sleep(0)

    assert backfiller.calls == [(0, 10, "node", 5)]
    assert provider._active_backfills == {}
    assert coordinator.complete_calls == 1
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


@pytest.mark.asyncio
async def test_schema_validation_error_blocks_response() -> None:
    schema = {"ts": "int64", "price": "float64"}
    provider = _DummyProvider(
        storage_source=_SchemaViolatingSource([(0, 10)], DataSourcePriority.STORAGE),
        conformance=_SchemaAwareConformance(schema),
    )

    with pytest.raises(ConformancePipelineError) as exc:
        await provider.fetch(0, 10, node_id="node", interval=5)

    report = exc.value.report
    assert any("dtype mismatch" in warning for warning in report.warnings)
    assert provider.last_conformance_report is report


class _DelayedSource(_StaticSource):
    def __init__(self, coverage, priority, clock: _FakeClock, delay: float) -> None:
        super().__init__(coverage, priority)
        self._clock = clock
        self._delay = delay

    async def coverage(self, *, node_id: str, interval: int) -> list[tuple[int, int]]:
        self._clock.advance(self._delay)
        return await super().coverage(node_id=node_id, interval=interval)

    async def fetch(self, start: int, end: int, *, node_id: str, interval: int) -> pd.DataFrame:
        self._clock.advance(self._delay)
        return await super().fetch(start, end, node_id=node_id, interval=interval)


class _SchemaAwareConformance(ConformancePipeline):
    def __init__(self, schema: dict[str, str]) -> None:
        super().__init__()
        self._schema = schema

    def normalize(self, df, schema=None, interval=None):  # type: ignore[override]
        return super().normalize(df, schema=self._schema, interval=interval)


class _SchemaViolatingSource(_StaticSource):
    async def fetch(self, start: int, end: int, *, node_id: str, interval: int) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "ts": [start, end],
                "price": ["oops", "nope"],
            }
        )


@pytest.mark.asyncio
async def test_sla_storage_budget_exceeded(monkeypatch) -> None:
    sdk_metrics.reset_metrics()
    clock = _FakeClock()
    monkeypatch.setattr(seamless_module.time, "monotonic", clock.monotonic)
    storage = _DelayedSource([(0, 200)], DataSourcePriority.STORAGE, clock, delay=0.05)
    provider = _DummyProvider(
        storage_source=storage,
        sla=SLAPolicy(max_wait_storage_ms=10),
    )

    with pytest.raises(SeamlessSLAExceeded) as exc:
        await provider.fetch(0, 100, node_id="node", interval=10)

    assert exc.value.phase == "storage_wait"


@pytest.mark.asyncio
async def test_sla_total_metric_recorded(monkeypatch) -> None:
    sdk_metrics.reset_metrics()
    clock = _FakeClock()
    monkeypatch.setattr(seamless_module.time, "monotonic", clock.monotonic)
    storage = _DelayedSource([(0, 20)], DataSourcePriority.STORAGE, clock, delay=0.002)
    provider = _DummyProvider(
        storage_source=storage,
        sla=SLAPolicy(max_wait_storage_ms=50, total_deadline_ms=100),
    )

    df = await provider.fetch(0, 20, node_id="node", interval=10)
    assert not df.empty
    key = ("node", "total")
    assert sdk_metrics.seamless_sla_deadline_seconds._vals[key]  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_sla_sync_gap_limit_enforced() -> None:
    sdk_metrics.reset_metrics()
    storage = _StaticSource([], DataSourcePriority.STORAGE)
    provider = _DummyProvider(
        storage_source=storage,
        sla=SLAPolicy(max_sync_gap_bars=1),
    )

    with pytest.raises(SeamlessSLAExceeded) as exc:
        await provider.ensure_data_available(0, 100, node_id="node", interval=10)

    assert exc.value.phase == "sync_gap"


@pytest.mark.asyncio
async def test_sla_total_deadline_breach_raises(monkeypatch) -> None:
    sdk_metrics.reset_metrics()
    clock = _FakeClock()
    monkeypatch.setattr(seamless_module.time, "monotonic", clock.monotonic)
    storage = _DelayedSource([(0, 20)], DataSourcePriority.STORAGE, clock, delay=0.04)
    provider = _DummyProvider(
        storage_source=storage,
        sla=SLAPolicy(max_wait_storage_ms=80, total_deadline_ms=50),
    )

    with pytest.raises(SeamlessSLAExceeded) as exc:
        await provider.fetch(0, 20, node_id="node", interval=10)

    assert exc.value.phase == "total"


@pytest.mark.asyncio
async def test_observability_snapshot_captures_backfill_failure(caplog) -> None:
    sdk_metrics.reset_metrics()
    backfiller = _FailingBackfiller()
    provider = _DummyProvider(
        storage_source=_StaticSource([], DataSourcePriority.STORAGE),
        backfiller=backfiller,
    )

    with caplog.at_level("ERROR", logger="qmtl.runtime.sdk.seamless_data_provider"):
        await provider._start_background_backfill(0, 20, node_id="node", interval=5)
        for _ in range(4):
            await asyncio.sleep(0)

    key = ("node", "5")
    assert sdk_metrics.backfill_failure_total._vals[key] == 1  # type: ignore[attr-defined]
    snapshot = sdk_metrics.collect_metrics()
    assert "backfill_failure_total" in snapshot
    assert 'node_id="node"' in snapshot

    failure_records = [
        record
        for record in caplog.records
        if record.getMessage().startswith("seamless.backfill.background_failed")
    ]
    assert failure_records, "expected structured failure log"
    record = failure_records[0]
    assert getattr(record, "node_id", None) == "node"
    assert getattr(record, "interval", None) == 5
    assert getattr(record, "start", None) == 0
    assert getattr(record, "end", None) == 20
