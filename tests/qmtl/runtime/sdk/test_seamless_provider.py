from __future__ import annotations

import asyncio
from datetime import datetime
import time
from typing import Optional, Any
import logging
import textwrap
from types import MethodType

import pandas as pd
import pytest
import json
from pathlib import Path

from qmtl.foundation.common.metrics_factory import get_mapping_store
from qmtl.foundation.config import DeploymentProfile, SeamlessConfig, UnifiedConfig
from qmtl.runtime.sdk.seamless_data_provider import (
    SeamlessDataProvider,
    DataSource,
    DataSourcePriority,
    ConformancePipelineError,
    SeamlessDomainPolicyError,
    BackfillConfig,
)
from qmtl.runtime.io.seamless_provider import (
    HistoryProviderDataSource,
    DataFetcherAutoBackfiller,
)
from qmtl.foundation.common.compute_context import ComputeContext
from qmtl.runtime.sdk import metrics as sdk_metrics
from qmtl.runtime.sdk.conformance import ConformancePipeline
from qmtl.runtime.sdk.artifacts import ArtifactPublication, FileSystemArtifactRegistrar
from qmtl.runtime.sdk.artifacts.fingerprint import compute_artifact_fingerprint
from qmtl.runtime.sdk import seamless_data_provider as seamless_module
from qmtl.runtime.sdk.sla import SLAPolicy, SLAViolationMode
from qmtl.runtime.sdk.exceptions import SeamlessSLAExceeded
from qmtl.runtime.sdk.backfill_coordinator import InMemoryBackfillCoordinator, Lease
from qmtl.runtime.sdk.configuration import (
    reset_runtime_config_cache,
    runtime_config_override,
)


def _store(metric):
    return get_mapping_store(metric, dict)


def _override_seamless(**kwargs: object):
    return runtime_config_override(UnifiedConfig(seamless=SeamlessConfig(**kwargs)))


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


class _CountingSource(_StaticSource):
    """Static source that tracks fetch calls for cache assertions."""

    def __init__(self, coverage: list[tuple[int, int]], priority: DataSourcePriority) -> None:
        super().__init__(coverage, priority)
        self.fetch_calls = 0

    async def fetch(self, start: int, end: int, *, node_id: str, interval: int) -> pd.DataFrame:
        self.fetch_calls += 1
        return await super().fetch(start, end, node_id=node_id, interval=interval)


class _DummyProvider(SeamlessDataProvider):
    """Concrete instance of SeamlessDataProvider using injected sources/backfiller."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("stabilization_bars", 0)
        super().__init__(*args, **kwargs)


class _FakeClock:
    def __init__(self) -> None:
        self._value = 0.0

    def monotonic(self) -> float:
        return self._value

    def time(self) -> float:
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


@pytest.mark.asyncio
async def test_subtract_ranges_without_interval_fallback() -> None:
    provider = _DummyProvider()
    remaining = provider._subtract_ranges(  # type: ignore[attr-defined]
        [(0, 100)],
        [(10, 20)],
        0,
    )
    assert remaining == [(0, 10), (20, 100)]


@pytest.mark.asyncio
async def test_subtract_ranges_alignment_guard() -> None:
    provider = _DummyProvider()
    remaining = provider._subtract_ranges(  # type: ignore[attr-defined]
        [(0, 40)],
        [(5, 25)],
        10,
    )
    assert remaining == [(0, 40)]


@pytest.mark.asyncio
async def test_fetch_response_includes_metadata() -> None:
    sdk_metrics.reset_metrics()
    storage = _StaticSource([(0, 100)], DataSourcePriority.STORAGE)
    registrar = _RecordingRegistrar()
    provider = _DummyProvider(
        storage_source=storage,
        registrar=registrar,
        stabilization_bars=1,
    )

    result = await provider.fetch(0, 100, node_id="node", interval=10)

    assert isinstance(result.metadata.dataset_fingerprint, str)
    assert result.metadata.dataset_fingerprint.startswith("sha256:")
    assert result.metadata.coverage_bounds == (0, 90)
    assert isinstance(result.metadata.as_of, str)
    # Validate ISO-8601 format
    datetime.fromisoformat(result.metadata.as_of.replace("Z", "+00:00"))
    assert registrar.calls and registrar.calls[0]["rows"] == len(result.frame)
    assert result.frame.attrs["dataset_fingerprint"] == result.metadata.dataset_fingerprint
    assert result.metadata.manifest_uri == "mem://manifest"
    assert result.metadata.artifact is not None
    assert result.metadata.artifact.manifest["producer"]["node_id"] == "node"
    assert result.metadata.conformance_version == seamless_module.CONFORMANCE_VERSION
    assert result.frame.attrs["conformance_version"] == seamless_module.CONFORMANCE_VERSION
    assert (
        result.metadata.artifact.manifest.get("conformance_version")
        == seamless_module.CONFORMANCE_VERSION
    )
    ratio_key = ("node", "10", "default")
    coverage_store = _store(sdk_metrics.coverage_ratio)
    staleness_store = _store(sdk_metrics.live_staleness_seconds)
    assert coverage_store[ratio_key]
    assert staleness_store[ratio_key] >= 0


@pytest.mark.asyncio
async def test_fetch_fingerprint_stable_across_calls() -> None:
    sdk_metrics.reset_metrics()
    storage = _StaticSource([(0, 100)], DataSourcePriority.STORAGE)
    registrar = _RecordingRegistrar()
    provider = _DummyProvider(
        storage_source=storage,
        registrar=registrar,
        stabilization_bars=1,
    )

    first = await provider.fetch(0, 100, node_id="node", interval=10)
    second = await provider.fetch(0, 100, node_id="node", interval=10)

    assert first.metadata.dataset_fingerprint == second.metadata.dataset_fingerprint
    assert len(registrar.calls) == 2
    collision_key = ("node", "10", "default")
    collision_store = _store(sdk_metrics.fingerprint_collisions)
    assert collision_store[collision_key] == 1


@pytest.mark.asyncio
async def test_publish_fingerprint_toggle_disables_publication() -> None:
    sdk_metrics.reset_metrics()
    storage = _StaticSource([(0, 100)], DataSourcePriority.STORAGE)
    registrar = _RecordingRegistrar()
    provider = _DummyProvider(
        storage_source=storage,
        registrar=registrar,
        stabilization_bars=1,
        publish_fingerprint=False,
    )

    result = await provider.fetch(0, 100, node_id="node", interval=10)

    assert result.metadata.dataset_fingerprint.startswith("sha256:")
    assert result.metadata.artifact is None
    assert registrar.calls and registrar.calls[0]["publish_fingerprint"] is False


@pytest.mark.asyncio
async def test_publish_toggle_respects_config() -> None:
    sdk_metrics.reset_metrics()
    storage = _StaticSource([(0, 100)], DataSourcePriority.STORAGE)
    registrar = _RecordingRegistrar()
    with _override_seamless(publish_fingerprint=False):
        provider = _DummyProvider(
            storage_source=storage,
            registrar=registrar,
            stabilization_bars=1,
        )

        result = await provider.fetch(0, 100, node_id="node", interval=10)

    assert result.metadata.dataset_fingerprint.startswith("sha256:")
    assert registrar.calls and registrar.calls[0]["publish_fingerprint"] is False


def test_publish_override_none_when_no_config(monkeypatch: pytest.MonkeyPatch) -> None:
    seamless_module._reset_publish_override_cache()
    monkeypatch.setattr(seamless_module, "get_runtime_config_path", lambda: None)

    override = seamless_module._read_publish_override_from_config()

    assert override is None
    assert seamless_module._PUBLISH_OVERRIDE_CACHE_LOADED is False


def test_publish_override_missing_file_cached(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    seamless_module._reset_publish_override_cache()
    missing = tmp_path / "qmtl.yml"
    monkeypatch.setattr(seamless_module, "get_runtime_config_path", lambda: str(missing))

    override = seamless_module._read_publish_override_from_config()

    assert override is None
    assert seamless_module._PUBLISH_OVERRIDE_CACHE_LOADED is True
    assert seamless_module._PUBLISH_OVERRIDE_CACHE_PATH == str(missing)


def test_coordinator_url_loaded_from_yaml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_path = tmp_path / "qmtl.yml"
    config_path.write_text(
        textwrap.dedent(
            """
            seamless:
              coordinator_url: https://coordinator.internal
            """
        )
    )

    created: dict[str, str] = {}

    class DummyCoordinator:
        def __init__(self, url: str) -> None:
            created["url"] = url

    monkeypatch.setattr(
        "qmtl.runtime.sdk.seamless_data_provider.DistributedBackfillCoordinator",
        DummyCoordinator,
    )
    monkeypatch.chdir(tmp_path)
    reset_runtime_config_cache()
    try:
        provider = _DummyProvider()
        assert created["url"] == "https://coordinator.internal"
        assert isinstance(provider._coordinator, DummyCoordinator)
    finally:
        reset_runtime_config_cache()


def test_prod_profile_requires_coordinator_url() -> None:
    reset_runtime_config_cache()
    config = UnifiedConfig(profile=DeploymentProfile.PROD, seamless=SeamlessConfig())

    with runtime_config_override(config):
        with pytest.raises(RuntimeError, match="seamless.coordinator_url"):
            _DummyProvider()

    reset_runtime_config_cache()


def test_prod_profile_rejects_unhealthy_coordinator(monkeypatch: pytest.MonkeyPatch) -> None:
    reset_runtime_config_cache()
    config = UnifiedConfig(
        profile=DeploymentProfile.PROD,
        seamless=SeamlessConfig(coordinator_url="http://coord"),
    )

    class _Result:
        ok = False
        code = "TIMEOUT"
        status = None
        err = "timeout"
        latency_ms = 50.0

    def _probe(url: str, *, attempts: int, backoff_seconds: float, timeout_seconds: float):
        assert attempts == 3
        assert backoff_seconds > 0
        assert timeout_seconds > 0
        return _Result()

    monkeypatch.setattr(
        "qmtl.runtime.sdk.seamless_data_provider.probe_coordinator_health",
        _probe,
    )

    with runtime_config_override(config):
        with pytest.raises(RuntimeError, match="health check failed"):
            _DummyProvider()

    reset_runtime_config_cache()


def test_dev_profile_falls_back_to_inmemory(monkeypatch: pytest.MonkeyPatch) -> None:
    reset_runtime_config_cache()
    config = UnifiedConfig(
        profile=DeploymentProfile.DEV,
        seamless=SeamlessConfig(coordinator_url=None),
    )

    with runtime_config_override(config):
        provider = _DummyProvider()

    assert isinstance(provider._coordinator, InMemoryBackfillCoordinator)
    reset_runtime_config_cache()


def test_prod_profile_uses_distributed_when_healthy(monkeypatch: pytest.MonkeyPatch) -> None:
    reset_runtime_config_cache()
    created: dict[str, str] = {}

    class _Result:
        ok = True
        code = "OK"
        status = 200
        err = None
        latency_ms = 1.0

    class DummyCoordinator:
        def __init__(self, url: str) -> None:
            created["url"] = url

    monkeypatch.setattr(
        "qmtl.runtime.sdk.seamless_data_provider.probe_coordinator_health",
        lambda *_args, **_kwargs: _Result(),
    )
    monkeypatch.setattr(
        "qmtl.runtime.sdk.seamless_data_provider.DistributedBackfillCoordinator",
        DummyCoordinator,
    )

    config = UnifiedConfig(
        profile=DeploymentProfile.PROD,
        seamless=SeamlessConfig(coordinator_url="http://coord"),
    )

    with runtime_config_override(config):
        provider = _DummyProvider()

    assert isinstance(provider._coordinator, DummyCoordinator)
    assert created["url"] == "http://coord"
    reset_runtime_config_cache()


def test_presets_file_loaded_from_yaml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    presets_path = tmp_path / "presets.yaml"
    presets_path.write_text(
        textwrap.dedent(
            """
            sla_presets:
              custom:
                policy:
                  max_lag_seconds: 120
            conformance_presets:
              strict:
                partial_ok: false
                schema:
                  fields:
                    - ts
                interval_ms: 60000
            """
        )
    )

    config_path = tmp_path / "qmtl.yml"
    config_path.write_text(
        textwrap.dedent(
            f"""
            seamless:
              presets_file: {presets_path.name}
              sla_preset: custom
              conformance_preset: strict
            """
        )
    )

    monkeypatch.chdir(tmp_path)
    reset_runtime_config_cache()
    try:
        provider = _DummyProvider(storage_source=_StaticSource([], DataSourcePriority.STORAGE))
        assert provider._sla is not None
        assert provider._sla.max_lag_seconds == 120
        assert provider._partial_ok is False
        assert provider._conformance_schema == {"fields": ["ts"]}
        assert provider._conformance_interval == 60
    finally:
        reset_runtime_config_cache()


def test_presets_file_missing_falls_back_to_empty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    missing = tmp_path / "absent_presets.yaml"
    config_path = tmp_path / "qmtl.yml"
    config_path.write_text("seamless:\n  presets_file: absent_presets.yaml\n")
    monkeypatch.chdir(tmp_path)
    reset_runtime_config_cache()
    try:
        config = SeamlessConfig(presets_file=str(missing))
        data, source = seamless_module._load_presets_document(config)
        assert data == {}
        assert source == str(missing)
    finally:
        reset_runtime_config_cache()


def test_presets_file_invalid_document_defaults_to_empty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    invalid = tmp_path / "presets.yaml"
    invalid.write_text("- not-a-mapping\n")
    config_path = tmp_path / "qmtl.yml"
    config_path.write_text("seamless:\n  presets_file: presets.yaml\n")
    monkeypatch.chdir(tmp_path)
    reset_runtime_config_cache()
    try:
        config = SeamlessConfig(presets_file=str(invalid))
        data, source = seamless_module._load_presets_document(config)
        assert data == {}
        assert source == str(invalid)
    finally:
        reset_runtime_config_cache()


@pytest.mark.asyncio
async def test_early_fingerprint_toggle_forwarded() -> None:
    sdk_metrics.reset_metrics()
    storage = _StaticSource([(0, 100)], DataSourcePriority.STORAGE)
    registrar = _RecordingRegistrar()
    provider = _DummyProvider(
        storage_source=storage,
        registrar=registrar,
        stabilization_bars=1,
        early_fingerprint=True,
    )

    result = await provider.fetch(0, 100, node_id="node", interval=10)

    assert result.metadata.dataset_fingerprint.startswith("sha256:")
    assert registrar.calls and registrar.calls[0]["early_fingerprint"] is True


@pytest.mark.asyncio
async def test_in_memory_cache_hits_same_context() -> None:
    sdk_metrics.reset_metrics()
    storage = _CountingSource([(0, 100)], DataSourcePriority.STORAGE)
    provider = _DummyProvider(
        storage_source=storage,
        cache={"enable": True, "ttl_ms": 60_000, "max_shards": 8},
    )

    first = await provider.fetch(
        0,
        100,
        node_id="node",
        interval=10,
        world_id="world-a",
        as_of="2024-01-01T00:00:00Z",
    )
    second = await provider.fetch(
        0,
        100,
        node_id="node",
        interval=10,
        world_id="world-a",
        as_of="2024-01-01T00:00:00Z",
    )

    assert storage.fetch_calls == 1
    assert first.metadata.cache_key == second.metadata.cache_key
    miss_key = ("node", "10", "world-a")
    hit_key = miss_key
    miss_store = _store(sdk_metrics.seamless_cache_miss_total)
    hit_store = _store(sdk_metrics.seamless_cache_hit_total)
    assert miss_store[miss_key] == 1
    assert hit_store[hit_key] == 1
    assert sdk_metrics.seamless_cache_resident_bytes._val > 0  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_in_memory_cache_recomputes_staleness(monkeypatch: pytest.MonkeyPatch) -> None:
    sdk_metrics.reset_metrics()
    fake_clock = _FakeClock()
    fake_clock.advance(120.0)
    monkeypatch.setattr(seamless_module.time, "time", fake_clock.time)
    monkeypatch.setattr(seamless_module.time, "monotonic", fake_clock.monotonic)

    with _override_seamless(sla_preset="", conformance_preset=""):
        storage = _CountingSource([(0, 100)], DataSourcePriority.STORAGE)
        provider = _DummyProvider(
            storage_source=storage,
            cache={"enable": True, "ttl_ms": 10_000_000, "max_shards": 8},
        )
        provider._cache_clock = fake_clock.monotonic  # type: ignore[attr-defined]

        first = await provider.fetch(
            0,
            100,
            node_id="node",
            interval=10,
            world_id="world-a",
            as_of="2024-01-01T00:00:00Z",
        )

        initial_staleness = first.metadata.staleness_ms

        fake_clock.advance(30.0)

        second = await provider.fetch(
            0,
            100,
            node_id="node",
            interval=10,
            world_id="world-a",
            as_of="2024-01-01T00:00:00Z",
        )

    assert storage.fetch_calls == 1
    assert initial_staleness is not None
    assert second.metadata.staleness_ms is not None
    assert second.metadata.staleness_ms == pytest.approx(initial_staleness + 30_000, rel=0, abs=1)
    assert second.metadata.downgraded is False


@pytest.mark.asyncio
async def test_in_memory_cache_includes_as_of_in_key() -> None:
    sdk_metrics.reset_metrics()
    storage = _CountingSource([(0, 100)], DataSourcePriority.STORAGE)
    provider = _DummyProvider(
        storage_source=storage,
        cache={"enable": True, "ttl_ms": 60_000, "max_shards": 8},
    )

    await provider.fetch(
        0,
        100,
        node_id="node",
        interval=10,
        world_id="world-a",
        as_of="2024-01-01T00:00:00Z",
    )
    await provider.fetch(
        0,
        100,
        node_id="node",
        interval=10,
        world_id="world-a",
        as_of="2024-01-02T00:00:00Z",
    )

    assert storage.fetch_calls == 2
    miss_key = ("node", "10", "world-a")
    miss_store = _store(sdk_metrics.seamless_cache_miss_total)
    assert miss_store[miss_key] == 2


@pytest.mark.asyncio
async def test_in_memory_cache_ttl_expiry() -> None:
    sdk_metrics.reset_metrics()
    fake_clock = _FakeClock()
    storage = _CountingSource([(0, 100)], DataSourcePriority.STORAGE)
    provider = _DummyProvider(
        storage_source=storage,
        cache={"enable": True, "ttl_ms": 1_000, "max_shards": 8},
    )
    provider._cache_clock = fake_clock.monotonic  # type: ignore[attr-defined]

    await provider.fetch(
        0,
        100,
        node_id="node",
        interval=10,
        world_id="world-a",
        as_of="2024-01-01T00:00:00Z",
    )
    fake_clock.advance(2.0)
    await provider.fetch(
        0,
        100,
        node_id="node",
        interval=10,
        world_id="world-a",
        as_of="2024-01-01T00:00:00Z",
    )

    assert storage.fetch_calls == 2
    miss_key = ("node", "10", "world-a")
    miss_store = _store(sdk_metrics.seamless_cache_miss_total)
    hit_store = _store(sdk_metrics.seamless_cache_hit_total)
    assert miss_store[miss_key] == 2
    assert hit_store.get(miss_key, 0) == 0
    assert sdk_metrics.seamless_cache_resident_bytes._val > 0  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_backtest_requires_as_of_context() -> None:
    storage = _StaticSource([(0, 100)], DataSourcePriority.STORAGE)
    provider = _DummyProvider(storage_source=storage)

    ctx = ComputeContext(world_id="world-a", execution_domain="backtest")
    with pytest.raises(SeamlessDomainPolicyError):
        await provider.fetch(0, 100, node_id="node", interval=10, compute_context=ctx)


@pytest.mark.asyncio
async def test_dryrun_requires_artifact_publication() -> None:
    storage = _StaticSource([(0, 100)], DataSourcePriority.STORAGE)
    provider = _DummyProvider(storage_source=storage, registrar=None)

    ctx = ComputeContext(
        world_id="world-dry",
        execution_domain="dryrun",
        as_of="2025-01-01T00:00:00Z",
    )

    with pytest.raises(SeamlessDomainPolicyError):
        await provider.fetch(0, 100, node_id="node", interval=10, compute_context=ctx)


@pytest.mark.asyncio
async def test_live_as_of_regression_triggers_hold_downgrade() -> None:
    sdk_metrics.reset_metrics()
    storage = _StaticSource([(0, 120)], DataSourcePriority.STORAGE)
    provider = _DummyProvider(storage_source=storage)

    ctx1 = ComputeContext(
        world_id="world-live",
        execution_domain="live",
        as_of="2025-01-01T00:00:00Z",
    )
    await provider.fetch(0, 120, node_id="node", interval=10, compute_context=ctx1)

    ctx2 = ComputeContext(
        world_id="world-live",
        execution_domain="live",
        as_of="2024-12-31T23:59:00Z",
    )
    result = await provider.fetch(
        0, 120, node_id="node", interval=10, compute_context=ctx2
    )

    assert result.metadata.downgraded is True
    assert result.metadata.downgrade_mode == SLAViolationMode.HOLD.value
    assert result.metadata.downgrade_reason == "as_of_regression"
    hold_key = ("node", "10", "default", "as_of_regression")
    hold_store = _store(sdk_metrics.domain_gate_holds)
    assert hold_store[hold_key] == 1


@pytest.mark.asyncio
async def test_live_as_of_advancement_metric_tracks_progression() -> None:
    sdk_metrics.reset_metrics()
    storage = _StaticSource([(0, 120)], DataSourcePriority.STORAGE)
    provider = _DummyProvider(storage_source=storage)

    ctx_initial = ComputeContext(
        world_id="world-live",
        execution_domain="live",
        as_of="2025-01-01T00:00:00Z",
    )
    await provider.fetch(0, 120, node_id="node", interval=10, compute_context=ctx_initial)

    metric_key = ("node", "world-live")
    advancement_store = _store(sdk_metrics.as_of_advancement_events)
    assert advancement_store[metric_key] == 1

    ctx_same = ComputeContext(
        world_id="world-live",
        execution_domain="live",
        as_of="2025-01-01T00:00:00Z",
    )
    await provider.fetch(0, 120, node_id="node", interval=10, compute_context=ctx_same)
    assert advancement_store[metric_key] == 1

    ctx_later = ComputeContext(
        world_id="world-live",
        execution_domain="live",
        as_of="2025-01-01T00:30:00Z",
    )
    await provider.fetch(0, 120, node_id="node", interval=10, compute_context=ctx_later)
    assert advancement_store[metric_key] == 2


@pytest.mark.asyncio
async def test_cache_key_includes_world_and_as_of() -> None:
    storage = _StaticSource([(0, 100)], DataSourcePriority.STORAGE)
    provider = _DummyProvider(storage_source=storage)

    ctx1 = ComputeContext(
        world_id="world-one",
        execution_domain="live",
        as_of="2025-01-01T00:00:00Z",
    )
    ctx2 = ComputeContext(
        world_id="world-two",
        execution_domain="live",
        as_of="2025-01-01T01:00:00Z",
    )

    result_one = await provider.fetch(
        0, 100, node_id="node", interval=10, compute_context=ctx1
    )
    result_two = await provider.fetch(
        0, 100, node_id="node", interval=10, compute_context=ctx2
    )

    assert result_one.metadata.cache_key != result_two.metadata.cache_key
    assert "world-one" in result_one.metadata.cache_key
    assert "world-two" in result_two.metadata.cache_key
    assert ctx1.as_of in result_one.metadata.cache_key  # type: ignore[arg-type]
    assert ctx2.as_of in result_two.metadata.cache_key  # type: ignore[arg-type]

    keys = set(provider._fingerprint_index.keys())  # type: ignore[attr-defined]
    expected_one = ("node", 10, "world-one", ctx1.as_of or "")
    expected_two = ("node", 10, "world-two", ctx2.as_of or "")
    assert expected_one in keys
    assert expected_two in keys


@pytest.mark.asyncio
async def test_filesystem_registrar_writes_manifest(tmp_path) -> None:
    sdk_metrics.reset_metrics()
    storage = _StaticSource([(0, 100)], DataSourcePriority.STORAGE)
    registrar = FileSystemArtifactRegistrar(tmp_path)
    provider = _DummyProvider(
        storage_source=storage,
        registrar=registrar,
        stabilization_bars=1,
    )

    result = await provider.fetch(0, 100, node_id="node", interval=10)

    manifest_path = Path(result.metadata.manifest_uri)
    assert manifest_path.exists()
    content = json.loads(manifest_path.read_text())
    assert content["dataset_fingerprint"] == result.metadata.dataset_fingerprint
    assert content["producer"]["node_id"] == "node"
    assert content["publication_watermark"].endswith("Z")
    data_uri = content["storage"]["data_uri"]
    assert data_uri.endswith("data.parquet") or data_uri.endswith("data.json")
    data_path = Path(data_uri)
    assert data_path.exists()
    latency_key = ("node", "10", "default")
    publish_latency_store = _store(sdk_metrics.artifact_publish_latency_ms)
    bytes_written_store = _store(sdk_metrics.artifact_bytes_written)
    assert publish_latency_store[latency_key]
    assert bytes_written_store[latency_key] > 0


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


class _ConcurrentBackfiller(_CountingBackfiller):
    """Backfiller that tracks the peak number of concurrent executions."""

    def __init__(self, storage_source: _StaticSource) -> None:
        super().__init__(storage_source)
        self.max_parallel = 0
        self._inflight = 0

    async def backfill(
        self,
        start: int,
        end: int,
        *,
        node_id: str,
        interval: int,
        target_storage: Optional[DataSource] = None,
    ) -> pd.DataFrame:
        self._inflight += 1
        try:
            self.max_parallel = max(self.max_parallel, self._inflight)
            return await super().backfill(
                start,
                end,
                node_id=node_id,
                interval=interval,
                target_storage=target_storage,
            )
        finally:
            # Yield to allow other tasks to run before marking completion
            await asyncio.sleep(0.01)
            self._inflight -= 1


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

    def __init__(
        self,
        error: Exception | None = None,
        *,
        exc: Exception | None = None,
    ) -> None:
        super().__init__()
        self._error = error or exc or RuntimeError("boom")

    async def backfill(
        self,
        start: int,
        end: int,
        *,
        node_id: str,
        interval: int,
        target_storage: Optional[DataSource] = None,
    ) -> pd.DataFrame:
        await super().backfill(
            start,
            end,
            node_id=node_id,
            interval=interval,
            target_storage=target_storage,
        )
        raise self._error


class _BlockingBackfiller(_RecordingBackfiller):
    """Backfiller that waits on an external event before completing."""

    def __init__(self, gate: asyncio.Event) -> None:
        super().__init__()
        self._gate = gate

    async def backfill(
        self,
        start: int,
        end: int,
        *,
        node_id: str,
        interval: int,
        target_storage: Optional[DataSource] = None,
    ) -> pd.DataFrame:
        await super().backfill(
            start,
            end,
            node_id=node_id,
            interval=interval,
            target_storage=target_storage,
        )
        await self._gate.wait()
        return pd.DataFrame([{"ts": start}, {"ts": end}])


class _FlakyBackfiller(_RecordingBackfiller):
    """Backfiller that fails a fixed number of times before succeeding."""

    def __init__(self, storage: _StaticSource, fail_times: int) -> None:
        super().__init__()
        self._storage = storage
        self._fail_times = fail_times

    async def backfill(
        self,
        start: int,
        end: int,
        *,
        node_id: str,
        interval: int,
        target_storage: Optional[DataSource] = None,
    ) -> pd.DataFrame:
        await super().backfill(
            start,
            end,
            node_id=node_id,
            interval=interval,
            target_storage=target_storage,
        )
        self._storage.add_range(start, end)
        if self._fail_times > 0:
            self._fail_times -= 1
            raise RuntimeError("transient_backfill_failure")
        return pd.DataFrame([{"ts": start}, {"ts": end}])


class _RecordingRegistrar:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def publish(
        self,
        frame: pd.DataFrame,
        *,
        node_id: str,
        interval: int,
        conformance_report: Any | None = None,
        requested_range: tuple[int, int] | None = None,
        publish_fingerprint: bool = True,
        early_fingerprint: bool = False,
    ) -> ArtifactPublication | None:
        coverage_bounds = (
            int(frame["ts"].min()),
            int(frame["ts"].max()),
        )
        record = {
            "node_id": node_id,
            "interval": interval,
            "coverage_bounds": coverage_bounds,
            "requested_range": requested_range,
            "rows": len(frame),
            "publish_fingerprint": publish_fingerprint,
            "early_fingerprint": early_fingerprint,
        }
        if conformance_report is not None:
            record["flags"] = dict(conformance_report.flags_counts)
            record["warnings"] = tuple(conformance_report.warnings)
        self.calls.append(record)
        if not publish_fingerprint:
            # Mimic ingestion workers that skip publication when disabled.
            return None
        fingerprint_metadata = {
            "node_id": node_id,
            "interval": int(interval),
            "coverage_bounds": coverage_bounds,
            "conformance_version": seamless_module.CONFORMANCE_VERSION,
        }
        fingerprint = compute_artifact_fingerprint(frame, fingerprint_metadata)
        manifest = {
            "node_id": node_id,
            "interval": int(interval),
            "range": [coverage_bounds[0], coverage_bounds[1]],
            "requested_range": list(requested_range or ()),
            "conformance_version": seamless_module.CONFORMANCE_VERSION,
            "dataset_fingerprint": fingerprint,
            "conformance": {
                "flags": dict(getattr(conformance_report, "flags_counts", {})),
                "warnings": list(getattr(conformance_report, "warnings", ())),
            },
            "manifest_uri": "mem://manifest",
            "storage": {
                "data_uri": "mem://data",
                "manifest_uri": "mem://manifest",
            },
            "producer": {"node_id": node_id, "interval": int(interval)},
        }
        return ArtifactPublication(
            dataset_fingerprint=fingerprint,
            as_of="2024-01-01T00:00:00Z",
            node_id=node_id,
            start=coverage_bounds[0],
            end=coverage_bounds[1],
            rows=len(frame),
            uri="mem://data",
            manifest_uri="mem://manifest",
            manifest=manifest,
        )


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


class _RecordingCoordinator:
    def __init__(self) -> None:
        self.claims: list[tuple[str, int]] = []
        self.completes: list[Lease] = []
        self.fails: list[tuple[Lease, str]] = []
        self.return_none_next = False
        self.raise_on_claim = False

    async def claim(self, key: str, lease_ms: int) -> Lease | None:
        self.claims.append((key, lease_ms))
        if self.raise_on_claim:
            self.raise_on_claim = False
            raise RuntimeError("claim failure")
        if self.return_none_next:
            self.return_none_next = False
            return None
        return Lease(key=key, token=f"token-{len(self.claims)}", lease_until_ms=lease_ms)

    async def complete(self, lease: Lease) -> None:
        self.completes.append(lease)

    async def fail(self, lease: Lease, reason: str) -> None:
        self.fails.append((lease, reason))

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
    last_ts_store = _store(sdk_metrics.backfill_last_timestamp)
    assert last_ts_store.get(key) == 100
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


@pytest.mark.asyncio
async def test_backfill_single_flight_ttl_expiration_allows_new_claim(monkeypatch) -> None:
    sdk_metrics.reset_metrics()
    storage = _StaticSource([], DataSourcePriority.STORAGE)
    gate = asyncio.Event()
    calls = 0
    backfiller = _RecordingBackfiller()
    config = BackfillConfig(single_flight_ttl_ms=60_000, distributed_lease_ttl_ms=60_000)
    provider = _DummyProvider(
        storage_source=storage,
        backfiller=backfiller,
        enable_background_backfill=True,
        backfill_config=config,
    )
    provider._coordinator = None  # type: ignore[attr-defined]

    async def _stub_execute(
        self,
        start: int,
        end: int,
        *,
        node_id: str,
        interval: int,
        target_storage: DataSource | None,
        sla_tracker: "_SLATracker | None" = None,
        collect_results: bool = False,
    ) -> list[pd.DataFrame]:
        nonlocal calls
        calls += 1
        await gate.wait()
        return []

    provider._execute_backfill_range = MethodType(_stub_execute, provider)  # type: ignore[attr-defined]

    await provider._start_background_backfill(0, 100, node_id="n", interval=10)
    await asyncio.sleep(0)
    assert calls == 1

    # TTL not yet expired → second invocation dedups while first still running
    await provider._start_background_backfill(0, 100, node_id="n", interval=10)
    await asyncio.sleep(0)
    assert calls == 1

    expiry_time = time.monotonic() + (config.single_flight_ttl_ms / 1000.0) + 0.05
    provider._cleanup_expired_backfills(now=expiry_time)  # type: ignore[attr-defined]

    await provider._start_background_backfill(0, 100, node_id="n", interval=10)
    await asyncio.sleep(0)
    assert calls == 2

    gate.set()


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

    class _StorageDS(HistoryProviderDataSource):
        def __init__(self, sp):
            super().__init__(sp, DataSourcePriority.STORAGE)

    storage_ds = _StorageDS(storage_provider)
    fetcher = _FakeFetcher()
    backfiller = DataFetcherAutoBackfiller(fetcher)

    df = await backfiller.backfill(0, 100, node_id="n", interval=10, target_storage=storage_ds)

    # Should use storage.fill_missing then storage.fetch once; never call fetcher
    assert storage_provider.filled == [(0, 100, "n", 10)]
    assert storage_provider.fetched == [(0, 100, "n", 10)]
    assert fetcher.calls == 0
    assert not df.empty and set(df["ts"]) == {0, 100}


class _FailingStorageProvider(_FakeStorageProvider):
    async def fill_missing(self, start: int, end: int, *, node_id: str, interval: int) -> None:  # pragma: no cover - exc path
        raise RuntimeError("storage down")


@pytest.mark.asyncio
async def test_storage_backfill_falls_back_to_fetcher(caplog) -> None:
    storage_provider = _FailingStorageProvider()

    class _StorageDS(HistoryProviderDataSource):
        def __init__(self, sp):
            super().__init__(sp, DataSourcePriority.STORAGE)

    storage_ds = _StorageDS(storage_provider)
    fetcher = _FakeFetcher()
    backfiller = DataFetcherAutoBackfiller(fetcher)

    caplog.set_level(logging.WARNING, logger="qmtl.runtime.io.seamless_provider")

    df = await backfiller.backfill(0, 50, node_id="n", interval=10, target_storage=storage_ds)

    fallback_logs = [r for r in caplog.records if r.getMessage() == "seamless.backfill.storage_fallback"]
    assert len(fallback_logs) == 1
    assert fallback_logs[0].source == "storage"
    assert fetcher.calls == 1
    assert not df.empty and df["ts"].tolist() == [0]


@pytest.mark.asyncio
async def test_data_fetcher_backfiller_logs_structured_success(caplog) -> None:
    storage_provider = _FakeStorageProvider()

    class _StorageDS(HistoryProviderDataSource):
        def __init__(self, sp):
            super().__init__(sp, DataSourcePriority.STORAGE)

    storage_ds = _StorageDS(storage_provider)
    fetcher = _FakeFetcher()
    backfiller = DataFetcherAutoBackfiller(fetcher)

    caplog.set_level(logging.INFO, logger="qmtl.runtime.io.seamless_provider")

    await backfiller.backfill(0, 100, node_id="n", interval=10, target_storage=storage_ds)

    attempt_logs = [
        record
        for record in caplog.records
        if record.getMessage() == "seamless.backfill.attempt"
    ]
    success_logs = [
        record
        for record in caplog.records
        if record.getMessage() == "seamless.backfill.succeeded"
    ]

    assert len(attempt_logs) == 1
    assert len(success_logs) == 1

    attempt_record = attempt_logs[0]
    success_record = success_logs[0]
    expected_batch_id = "n:10:0:100"

    assert attempt_record.batch_id == expected_batch_id
    assert attempt_record.attempt == 1
    assert attempt_record.source == "storage"

    assert success_record.batch_id == expected_batch_id
    assert success_record.attempt == 1
    assert success_record.source == "storage"


class _FailingFetcher(_FakeFetcher):
    async def fetch(self, start: int, end: int, *, node_id: str, interval: int) -> pd.DataFrame:
        raise RuntimeError("boom")


@pytest.mark.asyncio
async def test_data_fetcher_backfiller_logs_failure(caplog) -> None:
    fetcher = _FailingFetcher()
    backfiller = DataFetcherAutoBackfiller(fetcher)

    caplog.set_level(logging.INFO, logger="qmtl.runtime.io.seamless_provider")

    with pytest.raises(RuntimeError):
        await backfiller.backfill(0, 10, node_id="n", interval=5)

    failure_logs = [
        record
        for record in caplog.records
        if record.getMessage() == "seamless.backfill.failed"
    ]

    assert len(failure_logs) == 1
    failure_record = failure_logs[0]

    assert failure_record.batch_id == "n:5:0:10"
    assert failure_record.attempt == 1
    assert failure_record.source == "fetcher"
    assert failure_record.error == "boom"


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
    last_ts_store = _store(sdk_metrics.backfill_last_timestamp)
    gap_latency_store = _store(sdk_metrics.gap_repair_latency_ms)
    assert last_ts_store.get(key) == 100
    latency_key = ("n", "10", "default")
    assert gap_latency_store[latency_key]


@pytest.mark.asyncio
async def test_fetch_seamless_records_metrics_on_backfill() -> None:
    sdk_metrics.reset_metrics()
    storage = _StaticSource([], DataSourcePriority.STORAGE)
    backfiller = _CountingBackfiller(storage)
    provider = _DummyProvider(storage_source=storage, backfiller=backfiller)

    result = await provider.fetch(0, 100, node_id="n", interval=10)
    assert isinstance(result.frame, pd.DataFrame)
    key = ("n", "10")
    last_ts_store = _store(sdk_metrics.backfill_last_timestamp)
    gap_latency_store = _store(sdk_metrics.gap_repair_latency_ms)
    assert last_ts_store.get(key) == 100
    latency_key = ("n", "10", "default")
    assert gap_latency_store[latency_key]


@pytest.mark.asyncio
async def test_backfill_config_enforces_concurrency_cap() -> None:
    sdk_metrics.reset_metrics()
    storage = _StaticSource([], DataSourcePriority.STORAGE)
    backfiller = _ConcurrentBackfiller(storage)
    provider = _DummyProvider(
        storage_source=storage,
        backfiller=backfiller,
        enable_background_backfill=False,
        backfill_config=BackfillConfig(
            window_bars=1, max_concurrent_requests=2, max_attempts=1
        ),
    )

    ok = await provider.ensure_data_available(0, 100, node_id="n", interval=10)

    assert ok is True
    # With window_bars=1 and interval=10 we expect 10 chunks
    assert len(backfiller.calls) == 10
    assert backfiller.max_parallel <= 2


def test_backfill_config_sync_mode_forces_sync_execution() -> None:
    storage = _StaticSource([], DataSourcePriority.STORAGE)
    backfiller = _RecordingBackfiller()
    provider = _DummyProvider(
        storage_source=storage,
        backfiller=backfiller,
        enable_background_backfill=True,
        backfill_config=BackfillConfig(mode="sync"),
    )

    assert provider.enable_background_backfill is False


@pytest.mark.asyncio
async def test_backfill_retry_respects_zero_jitter_ratio(monkeypatch) -> None:
    sdk_metrics.reset_metrics()
    storage = _StaticSource([], DataSourcePriority.STORAGE)
    backfiller = _FlakyBackfiller(storage, fail_times=1)
    provider = _DummyProvider(
        storage_source=storage,
        backfiller=backfiller,
        enable_background_backfill=False,
        backfill_config=BackfillConfig(
            window_bars=1,
            max_attempts=2,
            retry_backoff_ms=10,
            jitter_ratio=0.0,
        ),
    )

    called = False

    def _flag_uniform(*args: float, **kwargs: float) -> float:
        nonlocal called
        called = True
        return 0.0

    monkeypatch.setattr(seamless_module.random, "uniform", _flag_uniform)

    ok = await provider.ensure_data_available(0, 20, node_id="n", interval=10)

    assert ok is True
    assert called is False
    retry_key = ("n", "10")
    retry_store = _store(sdk_metrics.backfill_retry_total)
    assert retry_store[retry_key] == 1


@pytest.mark.asyncio
async def test_backfill_retry_applies_jitter_ratio(monkeypatch) -> None:
    sdk_metrics.reset_metrics()
    storage = _StaticSource([], DataSourcePriority.STORAGE)
    backfiller = _FlakyBackfiller(storage, fail_times=1)
    provider = _DummyProvider(
        storage_source=storage,
        backfiller=backfiller,
        enable_background_backfill=False,
        backfill_config=BackfillConfig(
            window_bars=1,
            max_attempts=2,
            retry_backoff_ms=10,
            jitter_ratio=0.25,
        ),
    )

    jitter_calls: list[tuple[float, float]] = []
    monkeypatch.setattr(
        seamless_module.random,
        "uniform",
        lambda a, b: jitter_calls.append((a, b)) or 0.0,
    )

    original_sleep = seamless_module.asyncio.sleep
    sleep_durations: list[float] = []

    async def _fake_sleep(delay: float) -> None:
        sleep_durations.append(delay)
        await original_sleep(0)

    monkeypatch.setattr(seamless_module.asyncio, "sleep", _fake_sleep)

    ok = await provider.ensure_data_available(0, 20, node_id="n", interval=10)

    assert ok is True
    assert jitter_calls, "expected jitter sampling to occur"
    assert jitter_calls[0][0] == pytest.approx(0.0)
    assert jitter_calls[0][1] == pytest.approx(0.01 * 0.25)
    assert sleep_durations, "expected retry backoff sleep"
    assert pytest.approx(sleep_durations[0], rel=0.05) == 0.01


@pytest.mark.asyncio
async def test_conformance_pipeline_blocks_by_default() -> None:
    with _override_seamless(conformance_preset=""):
        provider = _DummyProvider(
            storage_source=_DuplicateSource([(0, 10)], DataSourcePriority.STORAGE),
            conformance=ConformancePipeline(),
        )

        with pytest.raises(ConformancePipelineError) as exc:
            await provider.fetch(0, 10, node_id="n", interval=10)

    report = exc.value.report
    assert report.warnings and "duplicate" in report.warnings[0]
    assert "duplicate_ts" in report.flags_counts
    assert provider.last_conformance_report is report


@pytest.mark.asyncio
async def test_conformance_pipeline_respects_partial_ok() -> None:
    with _override_seamless(conformance_preset=""):
        provider = _DummyProvider(
            storage_source=_DuplicateSource([(0, 10)], DataSourcePriority.STORAGE),
            conformance=ConformancePipeline(),
            partial_ok=True,
        )

        df = await provider.fetch(0, 10, node_id="n", interval=10)
    assert df["ts"].tolist() == [0]

    report = provider.last_conformance_report
    assert report is not None
    assert report.flags_counts.get("duplicate_ts") == 1


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
    sla_store = _store(sdk_metrics.seamless_sla_deadline_seconds)
    total_ms_store = _store(sdk_metrics.seamless_total_ms)
    storage_wait_store = _store(sdk_metrics.seamless_storage_wait_ms)
    assert sla_store[key]
    latency_key = ("node", "10", "default")
    assert total_ms_store[latency_key]
    assert storage_wait_store[latency_key]


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
async def test_sla_violation_partial_fill_downgrades(monkeypatch, caplog) -> None:
    sdk_metrics.reset_metrics()
    clock = _FakeClock()
    monkeypatch.setattr(seamless_module.time, "monotonic", clock.monotonic)
    storage = _DelayedSource([(0, 40)], DataSourcePriority.STORAGE, clock, delay=0.02)
    provider = _DummyProvider(
        storage_source=storage,
        sla=SLAPolicy(
            max_wait_storage_ms=5,
            on_violation=SLAViolationMode.PARTIAL_FILL,
        ),
    )

    with caplog.at_level("WARNING", logger="qmtl.runtime.sdk.seamless_data_provider"):
        result = await provider.fetch(0, 40, node_id="node", interval=10)

    assert result.metadata.downgraded is True
    assert result.metadata.downgrade_mode == SLAViolationMode.PARTIAL_FILL.value
    assert result.metadata.downgrade_reason == "sla_violation"
    violation = result.metadata.sla_violation
    assert violation is not None and violation["phase"] == "storage_wait"
    log_records = [r for r in caplog.records if r.getMessage() == "seamless.sla.downgrade"]
    assert log_records, "expected downgrade log"
    record = log_records[0]
    assert getattr(record, "dataset_fingerprint", None) == result.metadata.dataset_fingerprint
    assert getattr(record, "as_of", None) == result.metadata.as_of
    metric_key = ("node", "10", "default", "sla_violation")
    partial_fill_store = _store(sdk_metrics.partial_fill_returns)
    assert partial_fill_store[metric_key] == 1


@pytest.mark.asyncio
async def test_sla_min_coverage_enforces_hold() -> None:
    sdk_metrics.reset_metrics()
    storage = _StaticSource([(0, 40)], DataSourcePriority.STORAGE)
    provider = _DummyProvider(
        storage_source=storage,
        sla=SLAPolicy(
            on_violation=SLAViolationMode.PARTIAL_FILL,
            min_coverage=0.9,
        ),
    )

    result = await provider.fetch(0, 100, node_id="node", interval=10)

    assert result.metadata.downgraded is True
    assert result.metadata.downgrade_mode == SLAViolationMode.HOLD.value
    assert result.metadata.downgrade_reason == "coverage_breach"
    assert result.metadata.coverage_ratio is not None
    assert result.metadata.coverage_ratio < 0.9
    ratio_key = ("node", "10", "default")
    coverage_store = _store(sdk_metrics.coverage_ratio)
    hold_store = _store(sdk_metrics.domain_gate_holds)
    assert coverage_store[ratio_key] == result.metadata.coverage_ratio
    hold_key = ("node", "10", "default", "coverage_breach")
    assert hold_store[hold_key] == 1


@pytest.mark.asyncio
async def test_sla_max_lag_enforces_hold(monkeypatch) -> None:
    sdk_metrics.reset_metrics()
    storage = _StaticSource([(0, 100)], DataSourcePriority.STORAGE)
    provider = _DummyProvider(
        storage_source=storage,
        sla=SLAPolicy(
            on_violation=SLAViolationMode.PARTIAL_FILL,
            max_lag_seconds=1,
        ),
    )

    monkeypatch.setattr(seamless_module.time, "time", lambda: 10_000.0)

    result = await provider.fetch(0, 100, node_id="node", interval=10)

    assert result.metadata.downgraded is True
    assert result.metadata.downgrade_mode == SLAViolationMode.HOLD.value
    assert result.metadata.downgrade_reason == "freshness_breach"
    assert result.metadata.staleness_ms is not None
    assert result.metadata.staleness_ms > 1_000
    staleness_key = ("node", "10", "default")
    staleness_store = _store(sdk_metrics.live_staleness_seconds)
    hold_store = _store(sdk_metrics.domain_gate_holds)
    assert staleness_store[staleness_key] >= result.metadata.staleness_ms / 1000.0
    hold_key = ("node", "10", "default", "freshness_breach")
    assert hold_store[hold_key] == 1


@pytest.mark.asyncio
async def test_domain_gate_downgrade_includes_snapshot_metadata(caplog) -> None:
    sdk_metrics.reset_metrics()
    storage = _StaticSource([(0, 40)], DataSourcePriority.STORAGE)
    provider = _DummyProvider(storage_source=storage)

    compute_context = {
        "world_id": "world-live",
        "execution_domain": "live",
        "min_coverage": 0.95,
    }

    with caplog.at_level("WARNING", logger="qmtl.runtime.sdk.seamless_data_provider"):
        result = await provider.fetch(
            0,
            100,
            node_id="node",
            interval=10,
            compute_context=compute_context,
        )

    assert result.metadata.downgraded is True
    assert result.metadata.downgrade_reason == "coverage_breach"
    assert result.metadata.dataset_fingerprint is not None
    assert result.metadata.as_of is not None

    log_records = [
        record
        for record in caplog.records
        if record.getMessage() == "seamless.domain_gate.downgrade"
    ]
    assert log_records, "expected domain gate downgrade log"
    record = log_records[0]
    assert getattr(record, "dataset_fingerprint", None) == result.metadata.dataset_fingerprint
    assert getattr(record, "as_of", None) == result.metadata.as_of


@pytest.mark.asyncio
async def test_observability_snapshot_captures_backfill_failure(caplog) -> None:
    sdk_metrics.reset_metrics()
    backfiller = _FailingBackfiller()
    provider = _DummyProvider(
        storage_source=_StaticSource([], DataSourcePriority.STORAGE),
        backfiller=backfiller,
        backfill_config=BackfillConfig(max_attempts=1, retry_backoff_ms=0),
    )

    with caplog.at_level("ERROR", logger="qmtl.runtime.sdk.seamless_data_provider"):
        await provider._start_background_backfill(0, 20, node_id="node", interval=5)
        for _ in range(4):
            await asyncio.sleep(0)

    key = ("node", "5")
    failure_store = _store(sdk_metrics.backfill_failure_total)
    assert failure_store[key] == 1  # type: ignore[attr-defined]
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

@pytest.mark.asyncio
async def test_background_backfill_failure_marks_lease_failed() -> None:
    sdk_metrics.reset_metrics()
    storage = _StaticSource([], DataSourcePriority.STORAGE)
    backfiller = _FailingBackfiller(RuntimeError("background exploded"))
    coordinator = _RecordingCoordinator()
    provider = _DummyProvider(
        storage_source=storage,
        backfiller=backfiller,
        coordinator=coordinator,
        backfill_config=BackfillConfig(max_attempts=1, retry_backoff_ms=0),
    )

    ok = await provider.ensure_data_available(0, 100, node_id="node", interval=10)
    assert ok is False

    # Allow background task to run
    for _ in range(3):
        await asyncio.sleep(0)
    await asyncio.sleep(0.01)

    assert len(coordinator.claims) == 1
    assert not coordinator.completes
    assert len(coordinator.fails) == 1
    lease, reason = coordinator.fails[0]
    assert lease.key == "node:10:0:100::"
    assert "background_backfill_failed" in reason
    key = ("node", "10")
    failure_store = _store(sdk_metrics.backfill_failure_total)
    assert failure_store[key] == 1  # type: ignore[attr-defined]
    assert sdk_metrics.backfill_jobs_in_progress._val == 0  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_sync_backfill_claims_and_completes_lease() -> None:
    sdk_metrics.reset_metrics()
    storage = _StaticSource([], DataSourcePriority.STORAGE)
    backfiller = _CountingBackfiller(storage)
    coordinator = _RecordingCoordinator()
    provider = _DummyProvider(
        storage_source=storage,
        backfiller=backfiller,
        coordinator=coordinator,
        enable_background_backfill=False,
    )

    ok = await provider.ensure_data_available(0, 100, node_id="node", interval=10)
    assert ok is True
    assert len(backfiller.calls) == 1
    assert len(coordinator.claims) == 1
    assert len(coordinator.completes) == 1
    assert not coordinator.fails
    lease = coordinator.completes[0]
    assert lease.key == "node:10:0:100::"
    assert lease.token.startswith("token-")
    key = ("node", "10")
    last_ts_store = _store(sdk_metrics.backfill_last_timestamp)
    assert last_ts_store[key] == 100  # type: ignore[attr-defined]
    assert sdk_metrics.backfill_jobs_in_progress._val == 0  # type: ignore[attr-defined]
