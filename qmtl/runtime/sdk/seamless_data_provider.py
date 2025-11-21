from __future__ import annotations

from typing import (
    Protocol,
    AsyncIterator,
    Optional,
    Callable,
    Awaitable,
    TypeVar,
    Any,
    Sequence,
    Mapping,
    MutableMapping,
    Literal,
    cast,
)
from types import MappingProxyType
from abc import ABC
from collections import defaultdict, deque
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from importlib import resources
import inspect
import pandas as pd
from enum import Enum
import asyncio
import logging
import math
import os
from pathlib import Path
import time
import random
from asyncio import TaskGroup
from itertools import count

import yaml

from qmtl.foundation.config import SeamlessConfig
from qmtl.foundation.common.compute_context import normalize_context_value
from qmtl.runtime.sdk.configuration import (
    get_runtime_config_path,
    get_seamless_config,
)

from .history_coverage import (
    merge_coverage as _merge_coverage,
    compute_missing_ranges as _compute_missing_ranges,
    WarmupWindow,
)
from .data_io import HistoryProvider
from . import metrics as sdk_metrics
from .cache_lru import LRUCache
from .conformance import ConformancePipeline, ConformanceReport
from .backfill_coordinator import (
    BackfillCoordinator,
    DistributedBackfillCoordinator,
    InMemoryBackfillCoordinator,
    Lease,
)
from .sla import SLAPolicy, SLAViolationMode
from .exceptions import SeamlessSLAExceeded
from .artifacts import ArtifactRegistrar, ArtifactPublication
from .artifacts.fingerprint import (
    compute_artifact_fingerprint,
    compute_legacy_artifact_fingerprint,
)

logger = logging.getLogger(__name__)

"""Seamless Data Provider interfaces for transparent data access with auto-backfill."""

T = TypeVar("T")


CONFORMANCE_VERSION = "v2"


_FINGERPRINT_HISTORY_LIMIT = 32

_FINGERPRINT_MODE_CANONICAL = "canonical"
_FINGERPRINT_MODE_LEGACY = "legacy"

_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}

_PUBLISH_OVERRIDE_CACHE_PATH: str | None = None
_PUBLISH_OVERRIDE_CACHE_VALUE: bool | None = None
_PUBLISH_OVERRIDE_CACHE_LOADED: bool = False


def _coerce_bool(value: object | None, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in _TRUE_VALUES:
            return True
        if normalized in _FALSE_VALUES:
            return False
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    return default


def _reset_publish_override_cache() -> None:
    global _PUBLISH_OVERRIDE_CACHE_LOADED
    global _PUBLISH_OVERRIDE_CACHE_PATH
    global _PUBLISH_OVERRIDE_CACHE_VALUE

    _PUBLISH_OVERRIDE_CACHE_LOADED = False
    _PUBLISH_OVERRIDE_CACHE_PATH = None
    _PUBLISH_OVERRIDE_CACHE_VALUE = None


def _read_publish_override_from_config() -> bool | None:
    """Return publish override from the active config file when available."""

    path = get_runtime_config_path()
    if path is None:
        _reset_publish_override_cache()
        return None

    if _PUBLISH_OVERRIDE_CACHE_LOADED and path == _PUBLISH_OVERRIDE_CACHE_PATH:
        return _PUBLISH_OVERRIDE_CACHE_VALUE

    override = _load_publish_override(path)
    _cache_publish_override(path, override)
    return override


def _cache_publish_override(path: str, override: bool | None) -> None:
    global _PUBLISH_OVERRIDE_CACHE_LOADED
    global _PUBLISH_OVERRIDE_CACHE_PATH
    global _PUBLISH_OVERRIDE_CACHE_VALUE

    _PUBLISH_OVERRIDE_CACHE_LOADED = True
    _PUBLISH_OVERRIDE_CACHE_PATH = path
    _PUBLISH_OVERRIDE_CACHE_VALUE = override


def _load_publish_override(path: str) -> bool | None:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
    except FileNotFoundError:
        logger.debug("seamless.publish_config_missing", extra={"path": path})
        return None
    except OSError as exc:
        logger.debug(
            "seamless.publish_config_read_failed",
            extra={"path": path, "error": str(exc)},
        )
        return None
    except yaml.YAMLError as exc:
        logger.debug(
            "seamless.publish_config_parse_failed",
            extra={"path": path, "error": str(exc)},
        )
        return None

    if not isinstance(data, dict):
        logger.debug("seamless.publish_config_invalid", extra={"path": path})
        return None

    section = data.get("seamless")
    if not isinstance(section, dict):
        return None
    if "publish_fingerprint" not in section:
        return None
    return _coerce_bool(section.get("publish_fingerprint"), default=True)


def _resolve_publish_override(config: SeamlessConfig) -> bool | None:
    """Return the explicit publish override if one is configured."""

    env_value = os.getenv("QMTL_SEAMLESS_PUBLISH_FP")
    if env_value is not None:
        return _coerce_bool(env_value, default=True)

    file_override = _read_publish_override_from_config()
    if file_override is not None:
        return file_override

    field_default = type(config).__dataclass_fields__["publish_fingerprint"].default
    if config.publish_fingerprint != field_default:
        return bool(config.publish_fingerprint)

    return None


def _load_presets_document(config: SeamlessConfig) -> tuple[dict[str, Any], str | None]:
    """Return the parsed presets mapping and the source identifier."""

    data: dict[str, Any]
    source: str | None
    path = _resolve_presets_path(config)
    if path is not None:
        data, source = _load_presets_from_path(path)
        return data, source

    data, source = _load_packaged_presets()
    return data, source


def _resolve_presets_path(config: SeamlessConfig) -> Path | None:
    raw = getattr(config, "presets_file", None)
    if not raw:
        return None
    path = Path(raw)
    if path.is_absolute():
        return path
    base = get_runtime_config_path()
    if base:
        return Path(base).parent / path
    return path


def _load_presets_from_path(path: Path) -> tuple[dict[str, Any], str]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
    except FileNotFoundError:
        logger.warning("seamless.presets.missing_file", extra={"path": str(path)})
        return {}, str(path)
    except OSError as exc:
        logger.warning(
            "seamless.presets.read_failed",
            extra={"path": str(path), "error": str(exc)},
        )
        return {}, str(path)
    except yaml.YAMLError as exc:
        logger.warning(
            "seamless.presets.parse_failed",
            extra={"path": str(path), "error": str(exc)},
        )
        return {}, str(path)

    if not isinstance(data, dict):
        logger.warning("seamless.presets.invalid_document", extra={"path": str(path)})
        return {}, str(path)
    return data, str(path)


def _load_packaged_presets() -> tuple[dict[str, Any], str | None]:
    try:
        resource = resources.files("qmtl.examples.seamless").joinpath("presets.yaml")
    except AttributeError:  # pragma: no cover - older Python fallback
        resource = None

    if resource is None:
        return {}, None

    try:
        with resource.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
        if not isinstance(data, dict):
            logger.warning("seamless.presets.invalid_document", extra={"path": str(resource)})
            return {}, str(resource)
        return data, str(resource)
    except FileNotFoundError:
        logger.warning("seamless.presets.packaged_missing")
    except OSError as exc:
        logger.warning("seamless.presets.packaged_read_failed", extra={"error": str(exc)})
    except yaml.YAMLError as exc:
        logger.warning("seamless.presets.packaged_parse_failed", extra={"error": str(exc)})
    return {}, str(resource)


def _resolve_sla_preset(data: dict[str, Any], config: SeamlessConfig) -> SLAPolicy | None:
    key = getattr(config, "sla_preset", None)
    if not key:
        return None
    presets = data.get("sla_presets")
    if not isinstance(presets, dict):
        return None
    entry = presets.get(key)
    if not isinstance(entry, dict):
        logger.warning("seamless.presets.sla_missing", extra={"preset": key})
        return None
    policy = entry.get("policy")
    if not isinstance(policy, dict):
        logger.warning("seamless.presets.sla_invalid", extra={"preset": key})
        return None
    try:
        return SLAPolicy(**policy)
    except Exception as exc:  # pragma: no cover - defensive guard
        logger.warning(
            "seamless.presets.sla_error", extra={"preset": key, "error": str(exc)}
        )
        return None


def _resolve_conformance_preset(
    data: dict[str, Any], config: SeamlessConfig
) -> tuple[bool | None, dict[str, Any] | None, int | None]:
    key = getattr(config, "conformance_preset", None)
    if not key:
        return None, None, None
    presets = data.get("conformance_presets")
    if not isinstance(presets, dict):
        return None, None, None
    entry = presets.get(key)
    if not isinstance(entry, dict):
        logger.warning(
            "seamless.presets.conformance_missing", extra={"preset": key}
        )
        return None, None, None
    partial_raw = entry.get("partial_ok")
    partial_ok: bool | None
    if isinstance(partial_raw, bool):
        partial_ok = partial_raw
    elif isinstance(partial_raw, str):
        partial_ok = _coerce_bool(partial_raw, default=False)
    else:
        partial_ok = None
    schema = entry.get("schema") if isinstance(entry.get("schema"), dict) else None
    interval_raw = entry.get("interval_ms")
    interval_ms: int | None
    if isinstance(interval_raw, (int, float)):
        try:
            interval_ms = int(interval_raw)
        except (TypeError, ValueError):  # pragma: no cover - defensive
            interval_ms = None
    else:
        interval_ms = None
    return partial_ok, schema, interval_ms
@dataclass(slots=True)
class SeamlessFetchMetadata:
    node_id: str
    interval: int
    requested_range: tuple[int, int]
    rows: int
    coverage_bounds: tuple[int, int] | None
    conformance_flags: dict[str, int]
    conformance_warnings: tuple[str, ...]
    conformance_version: str = CONFORMANCE_VERSION
    dataset_fingerprint: str | None = None
    as_of: int | str | None = None
    manifest_uri: str | None = None
    artifact: ArtifactPublication | None = None
    downgraded: bool = False
    downgrade_mode: str | None = None
    downgrade_reason: str | None = None
    sla_violation: dict[str, Any] | None = None
    coverage_ratio: float | None = None
    staleness_ms: float | None = None
    world_id: str | None = None
    execution_domain: str | None = None
    requested_as_of: str | None = None
    cache_key: str | None = None


@dataclass(slots=True)
class SeamlessFetchResult:
    frame: pd.DataFrame
    metadata: SeamlessFetchMetadata

    def __getattr__(self, item: str) -> Any:
        return getattr(self.frame, item)

    def __getitem__(self, key: Any) -> Any:
        return self.frame.__getitem__(key)

    def __iter__(self):
        return iter(self.frame)

    def __len__(self) -> int:
        return len(self.frame)


@dataclass(slots=True)
class _SLAViolationDetail:
    phase: str
    elapsed_ms: float
    budget_ms: int | None


@dataclass(slots=True)
class _DowngradeDecision:
    mode: SLAViolationMode
    reason: str
    violation: _SLAViolationDetail | None
    coverage_ratio: float | None
    staleness_ms: float | None


@dataclass(slots=True)
class _PublicationContext:
    fingerprint: str | None
    coverage_bounds: tuple[int, int] | None
    manifest_uri: str | None
    publication: ArtifactPublication | None
    as_of: str


@dataclass(slots=True)
class _CacheEntry:
    result: "SeamlessFetchResult"
    report: ConformanceReport | None
    resident_bytes: int
    world_id: str | None


@dataclass(slots=True)
class _ConformanceDefaults:
    sla: SLAPolicy | None
    partial_ok: bool
    schema: dict[str, Any] | None
    interval: int | None


@dataclass(slots=True)
class _BackfillSettings:
    config: BackfillConfig
    background_enabled: bool
    coordinator: BackfillCoordinator


@dataclass(slots=True)
class _FingerprintSettings:
    publish: bool
    early: bool
    preview: bool
    mode: str


@dataclass(slots=True)
class _RequestContext:
    """Normalized compute context associated with a fetch call."""

    world_id: str
    execution_domain: str
    requested_as_of: str | None
    min_coverage: float | None
    max_lag_seconds: float | None

    def key_components(self) -> tuple[str, str]:
        return self.world_id, self.requested_as_of or ""


@dataclass(slots=True)
class BackfillConfig:
    """Configuration for coordinating backfill execution."""

    mode: Literal["background", "sync"] = "background"
    single_flight_ttl_ms: int = 60_000
    distributed_lease_ttl_ms: int = 120_000
    window_bars: int = 900
    max_concurrent_requests: int = 8
    max_attempts: int = 6
    retry_backoff_ms: int = 500
    jitter_ratio: float = 0.25


class SeamlessDomainPolicyError(RuntimeError):
    """Raised when domain gating policies reject a fetch."""


class DataAvailabilityStrategy(Enum):
    """Strategy for handling data availability gaps."""
    FAIL_FAST = "fail_fast"  # Raise exception if data not available
    AUTO_BACKFILL = "auto_backfill"  # Automatically backfill missing data
    PARTIAL_FILL = "partial_fill"  # Return available data, backfill in background
    SEAMLESS = "seamless"  # Transparent combination of all sources


class DataSourcePriority(Enum):
    """Priority levels for data sources."""
    CACHE = 1      # In-memory/local cache (fastest)
    STORAGE = 2    # Historical storage (fast)
    BACKFILL = 3   # Auto-backfill from external sources (slower)
    LIVE = 4       # Live data feed (variable latency)


class DataSource(Protocol):
    """Base protocol for all data sources."""
    
    priority: DataSourcePriority
    
    async def is_available(
        self, start: int, end: int, *, node_id: str, interval: int
    ) -> bool:
        """Check if data is available for the given range."""
        ...
    
    async def fetch(
        self, start: int, end: int, *, node_id: str, interval: int
    ) -> pd.DataFrame:
        """Fetch data for the given range."""
        ...
    
    async def coverage(
        self, *, node_id: str, interval: int
    ) -> list[tuple[int, int]]:
        """Return timestamp ranges available."""
        ...


class AutoBackfiller(Protocol):
    """Protocol for automatic data backfilling."""
    
    async def can_backfill(
        self, start: int, end: int, *, node_id: str, interval: int
    ) -> bool:
        """Check if backfill is possible for the given range."""
        ...
    
    async def backfill(
        self, start: int, end: int, *, node_id: str, interval: int,
        target_storage: Optional[DataSource] = None
    ) -> pd.DataFrame:
        """Backfill data and optionally store in target storage."""
        ...
    
    async def backfill_async(
        self, start: int, end: int, *, node_id: str, interval: int,
        target_storage: Optional[DataSource] = None,
        progress_callback: Optional[Callable[[float], None]] = None
    ) -> AsyncIterator[pd.DataFrame]:
        """Backfill data asynchronously with progress updates."""
        ...


class LiveDataFeed(Protocol):
    """Protocol for live data feeds."""
    
    async def is_live_available(
        self, *, node_id: str, interval: int
    ) -> bool:
        """Check if live data is available for the node."""
        ...
    
    async def subscribe(
        self, *, node_id: str, interval: int
    ) -> AsyncIterator[tuple[int, pd.DataFrame]]:
        """Subscribe to live data stream."""
        ...


class ConformancePipelineError(RuntimeError):
    """Raised when the conformance pipeline blocks a response."""

    def __init__(self, report: ConformanceReport) -> None:
        self.report = report
        warning_count = len(report.warnings)
        flag_count = sum(report.flags_counts.values())
        message = (
            "conformance pipeline blocked response"
            f" (warnings={warning_count}, flags={flag_count})"
        )
        super().__init__(message)


class SeamlessDataProvider(HistoryProvider):
    """
    Provides transparent data access across multiple sources.
    
    This class implements the core logic for seamless data provision:
    1. Try cache first (fastest)
    2. Try historical storage
    3. Auto-backfill missing data if configured
    4. Fall back to live data if available
    
    All operations are transparent to the consumer.
    """
    
    def __init__(
        self,
        *,
        strategy: DataAvailabilityStrategy = DataAvailabilityStrategy.SEAMLESS,
        cache_source: Optional[DataSource] = None,
        storage_source: Optional[DataSource] = None,
        backfiller: Optional[AutoBackfiller] = None,
        live_feed: Optional[LiveDataFeed] = None,
        max_backfill_chunk_size: int = 1000,
        enable_background_backfill: bool = True,
        conformance: Optional[ConformancePipeline] = None,
        coordinator: Optional[BackfillCoordinator] = None,
        sla: Optional[SLAPolicy] = None,
        partial_ok: bool | None = None,
        registrar: ArtifactRegistrar | None = None,
        stabilization_bars: int = 2,
        backfill_config: BackfillConfig | None = None,
        cache: Mapping[str, Any] | None = None,
        publish_fingerprint: bool | None = None,
        early_fingerprint: bool | None = None,
        seamless_config: SeamlessConfig | None = None,
    ) -> None:
        self.strategy = strategy
        self.cache_source = cache_source
        self.storage_source = storage_source
        self.backfiller = backfiller
        self.live_feed = live_feed
        self.max_backfill_chunk_size = max_backfill_chunk_size
        config = seamless_config or get_seamless_config()
        self._seamless_config = config

        conformance_defaults = self._build_conformance_defaults(
            config=config,
            sla=sla,
            partial_ok=partial_ok,
        )
        self._conformance = conformance
        self._conformance_schema: dict[str, Any] | None = (
            conformance_defaults.schema
        )
        self._conformance_interval: int | None = conformance_defaults.interval
        self._sla = conformance_defaults.sla
        self._partial_ok = conformance_defaults.partial_ok

        backfill_settings = self._init_backfill_policy(
            backfill_config=backfill_config,
            enable_background_backfill=enable_background_backfill,
            coordinator=coordinator,
            max_backfill_chunk_size=max_backfill_chunk_size,
        )
        self._backfill_config = backfill_settings.config
        self.enable_background_backfill = backfill_settings.background_enabled
        self._coordinator = backfill_settings.coordinator
        self._last_conformance_report: Optional[ConformanceReport] = None
        self._registrar = registrar
        self._stabilization_bars = max(0, int(stabilization_bars))
        # Preserve last fetch metadata for introspection
        self._last_fetch_metadata: Optional[SeamlessFetchMetadata] = None

        # Internal state
        self._active_backfills: dict[str, tuple[float, int]] = {}
        self._backfill_generation = count()
        self._fingerprint_window_limit = _FINGERPRINT_HISTORY_LIMIT
        self._fingerprint_index: dict[tuple[str, int, str, str], deque[str]] = defaultdict(
            self._create_fingerprint_window
        )
        self._live_as_of_state: dict[tuple[str, str], str] = {}
        self._domain_gate_evaluator = _DomainGateEvaluator(
            merge_decisions=self._merge_decisions,
            compute_coverage_ratio=self._compute_coverage_ratio,
            compute_staleness_ms=self._compute_staleness_ms,
            compare_as_of=self._compare_as_of,
            live_state=self._live_as_of_state,
            logger=logger,
        )

        fingerprint_settings = self._configure_fingerprint_mode(
            config=config,
            publish_override=publish_fingerprint,
            early_override=early_fingerprint,
        )
        self._publish_fingerprint = fingerprint_settings.publish
        self._early_fingerprint = fingerprint_settings.early
        self._fingerprint_mode = fingerprint_settings.mode
        self._preview_fingerprint = fingerprint_settings.preview

        cache_config = cache or {}
        template_default = "{node_id}:{start}:{end}:{interval}:{conformance_version}:{world_id}:{as_of}"
        self._cache_key_template = str(cache_config.get("key_template", template_default))
        self._cache_clock: Callable[[], float] = time.monotonic
        self._cache_enabled = bool(cache_config.get("enable"))
        self._cache: LRUCache[str, _CacheEntry] | None = None
        if self._cache_enabled:
            ttl_ms = max(0, int(cache_config.get("ttl_ms", 60_000)))
            max_shards = max(1, int(cache_config.get("max_shards", 256)))
            self._cache = LRUCache(
                max_entries=max_shards,
                ttl_ms=ttl_ms,
                clock=self._cache_now,
            )
        else:
            sdk_metrics.observe_seamless_cache_resident_bytes(0)

    def _validate_node_id(self, node_id: str) -> None:
        """Hook for subclasses to validate node identifiers."""

        return None

    @property
    def last_conformance_report(self) -> Optional[ConformanceReport]:
        """Return the most recent conformance report emitted by ``fetch``."""

        return self._last_conformance_report

    @property
    def last_fetch_metadata(self) -> Optional[SeamlessFetchMetadata]:
        """Return metadata describing the last call to :meth:`fetch`."""

        return self._last_fetch_metadata

    def _build_conformance_defaults(
        self,
        *,
        config: SeamlessConfig,
        sla: SLAPolicy | None,
        partial_ok: bool | None,
    ) -> _ConformanceDefaults:
        presets_data, _ = _load_presets_document(config)
        preset_sla = _resolve_sla_preset(presets_data, config)
        (
            preset_partial_ok,
            preset_schema,
            preset_interval_ms,
        ) = _resolve_conformance_preset(presets_data, config)

        resolved_partial_flag = (
            partial_ok if partial_ok is not None else preset_partial_ok
        )

        interval_value: int | None = None
        if preset_interval_ms is not None:
            try:
                candidate = int(preset_interval_ms)
            except (TypeError, ValueError):  # pragma: no cover - defensive
                candidate = None
            if candidate is not None and candidate > 0:
                if candidate % 1000 == 0:
                    candidate //= 1000
                interval_value = candidate

        return _ConformanceDefaults(
            sla=sla or preset_sla,
            partial_ok=bool(resolved_partial_flag),
            schema=preset_schema,
            interval=interval_value,
        )

    def _init_backfill_policy(
        self,
        *,
        backfill_config: BackfillConfig | None,
        enable_background_backfill: bool,
        coordinator: BackfillCoordinator | None,
        max_backfill_chunk_size: int,
    ) -> _BackfillSettings:
        effective_config = self._normalize_backfill_config(
            backfill_config
            if backfill_config is not None
            else BackfillConfig(window_bars=max_backfill_chunk_size)
        )
        background_enabled = bool(enable_background_backfill) and (
            effective_config.mode == "background"
        )
        resolved_coordinator = coordinator or self._create_default_coordinator()
        return _BackfillSettings(
            config=effective_config,
            background_enabled=background_enabled,
            coordinator=resolved_coordinator,
        )

    def _configure_fingerprint_mode(
        self,
        *,
        config: SeamlessConfig,
        publish_override: bool | None,
        early_override: bool | None,
    ) -> _FingerprintSettings:
        mode_value = str(config.fingerprint_mode or "").strip().lower()
        legacy_requested = mode_value == _FINGERPRINT_MODE_LEGACY
        canonical_requested = mode_value == _FINGERPRINT_MODE_CANONICAL

        publish_override_value = _resolve_publish_override(config)
        if publish_override_value is None:
            publish_default = _coerce_bool(
                config.publish_fingerprint,
                default=True,
            )
            if legacy_requested:
                publish_default = False
        else:
            publish_default = publish_override_value

        publish_flag = _coerce_bool(
            publish_override,
            default=publish_default,
        )

        early_default = _coerce_bool(config.early_fingerprint, default=False)
        early_flag = _coerce_bool(
            early_override,
            default=early_default,
        )

        if canonical_requested or legacy_requested:
            fingerprint_mode = mode_value or (
                _FINGERPRINT_MODE_CANONICAL
                if publish_flag
                else _FINGERPRINT_MODE_LEGACY
            )
        else:
            fingerprint_mode = (
                _FINGERPRINT_MODE_CANONICAL
                if publish_flag
                else _FINGERPRINT_MODE_LEGACY
            )

        preview_flag = _coerce_bool(config.preview_fingerprint, default=False)

        return _FingerprintSettings(
            publish=publish_flag,
            early=early_flag,
            preview=preview_flag or early_flag,
            mode=fingerprint_mode,
        )

    def _create_default_coordinator(self) -> BackfillCoordinator:
        url = (self._seamless_config.coordinator_url or "").strip()
        if url:
            try:
                return DistributedBackfillCoordinator(url)
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("seamless.coordinator.init_failed", exc_info=exc)
        return InMemoryBackfillCoordinator()

    def _cache_now(self) -> float:
        clock = self._cache_clock
        return float(clock())

    def _build_sla_tracker(self, node_id: str, interval: int) -> "_SLATracker | None":
        if not self._sla:
            return None
        return _SLATracker(self._sla, node_id=node_id, interval=int(interval))

    def _create_fingerprint_window(self) -> deque[str]:
        return deque(maxlen=self._fingerprint_window_limit)

    def _cache_available(self) -> bool:
        return self._cache is not None

    def _cache_lookup(
        self,
        key: str,
        *,
        node_id: str,
        interval: int,
        world_id: str | None,
    ) -> _CacheEntry | None:
        if self._cache is None:
            return None
        entry = self._cache.get(key)
        if entry is None:
            sdk_metrics.observe_seamless_cache_miss(
                node_id=node_id, interval=interval, world_id=world_id
            )
            self._update_cache_resident_bytes()
            return None
        sdk_metrics.observe_seamless_cache_hit(
            node_id=node_id, interval=interval, world_id=world_id
        )
        return cast(_CacheEntry, entry)

    def _update_cache_resident_bytes(self) -> None:
        if self._cache is None:
            sdk_metrics.observe_seamless_cache_resident_bytes(0)
            return
        self._cache.prune()
        sdk_metrics.observe_seamless_cache_resident_bytes(self._cache.resident_bytes)

    def _cache_store(
        self,
        key: str,
        entry: _CacheEntry,
    ) -> None:
        if self._cache is None:
            return
        self._cache.set(key, entry, weight=entry.resident_bytes)
        self._update_cache_resident_bytes()

    def _cache_snapshot(
        self,
        key: str,
        response: SeamlessFetchResult,
        *,
        world_id: str | None,
    ) -> None:
        if self._cache is None:
            return
        stored_frame = response.frame.copy(deep=True)
        stored_metadata = replace(response.metadata)
        self._sync_metadata_attrs(stored_frame, stored_metadata)
        stored_result = SeamlessFetchResult(stored_frame, stored_metadata)
        resident_bytes = int(stored_frame.memory_usage(deep=True).sum()) if not stored_frame.empty else 0
        entry = _CacheEntry(
            result=stored_result,
            report=self._last_conformance_report,
            resident_bytes=resident_bytes,
            world_id=world_id,
        )
        self._cache_store(key, entry)

    def _materialize_cached_result(self, entry: _CacheEntry) -> SeamlessFetchResult:
        frame_copy = entry.result.frame.copy(deep=True)
        metadata_copy = replace(entry.result.metadata)
        metadata_copy.downgraded = False
        metadata_copy.downgrade_mode = None
        metadata_copy.downgrade_reason = None
        metadata_copy.sla_violation = None
        if metadata_copy.coverage_bounds is not None:
            metadata_copy.staleness_ms = self._compute_staleness_ms(metadata_copy)
        else:
            metadata_copy.staleness_ms = None
        self._sync_metadata_attrs(frame_copy, metadata_copy)
        result = SeamlessFetchResult(frame_copy, metadata_copy)
        self._last_conformance_report = entry.report
        self._last_fetch_metadata = metadata_copy
        return result

    def _normalize_backfill_config(self, config: BackfillConfig) -> BackfillConfig:
        mode = config.mode if config.mode in {"background", "sync"} else "background"
        ttl = max(0, int(config.single_flight_ttl_ms))
        lease_ttl = max(0, int(config.distributed_lease_ttl_ms))
        window_bars = max(0, int(config.window_bars))
        concurrent = max(1, int(config.max_concurrent_requests))
        max_attempts = max(1, int(config.max_attempts))
        retry_backoff = max(0, int(config.retry_backoff_ms))
        jitter_raw = config.jitter_ratio
        try:
            jitter_ratio = float(jitter_raw)
        except (TypeError, ValueError):
            jitter_ratio = 0.0
        if not math.isfinite(jitter_ratio):
            jitter_ratio = 0.0
        jitter_ratio = max(0.0, min(1.0, jitter_ratio))
        return BackfillConfig(
            mode=mode,
            single_flight_ttl_ms=ttl,
            distributed_lease_ttl_ms=lease_ttl,
            window_bars=window_bars,
            max_concurrent_requests=concurrent,
            max_attempts=max_attempts,
            retry_backoff_ms=retry_backoff,
            jitter_ratio=jitter_ratio,
        )

    def _cleanup_expired_backfills(self, now: float | None = None) -> None:
        if not self._active_backfills:
            return
        current_time = time.monotonic() if now is None else now
        expired_keys = [
            key
            for key, (expires_at, _token) in self._active_backfills.items()
            if expires_at <= current_time
        ]
        for key in expired_keys:
            self._active_backfills.pop(key, None)

    def _chunk_backfill_ranges(
        self, start: int, end: int, interval: int
    ) -> list[tuple[int, int]]:
        if end <= start:
            return [(start, end)]
        bars = self._backfill_config.window_bars
        if interval <= 0 or bars <= 0:
            return [(start, end)]
        chunk_span = int(interval) * int(bars)
        if chunk_span <= 0:
            return [(start, end)]
        chunks: list[tuple[int, int]] = []
        current = int(start)
        final_end = int(end)
        while current < final_end:
            chunk_end = current + chunk_span
            if chunk_end >= final_end:
                chunks.append((current, final_end))
                break
            chunks.append((current, chunk_end))
            if chunk_end == current:
                break
            current = chunk_end
        if not chunks:
            chunks.append((start, end))
        return chunks

    async def _run_backfill_chunks(
        self,
        chunks: Sequence[tuple[int, int]],
        *,
        node_id: str,
        interval: int,
        target_storage: DataSource | None,
        sla_tracker: "_SLATracker | None",
        collect_results: bool,
    ) -> list[pd.DataFrame]:
        if not chunks:
            return []

        semaphore = asyncio.Semaphore(
            max(1, int(self._backfill_config.max_concurrent_requests))
        )
        if sla_tracker is not None:
            semaphore = asyncio.Semaphore(1)

        base_delay = self._backfill_config.retry_backoff_ms / 1000.0
        jitter_ratio = float(self._backfill_config.jitter_ratio)
        jitter_enabled = base_delay > 0 and jitter_ratio > 0
        max_attempts = max(1, int(self._backfill_config.max_attempts))

        results: dict[int, pd.DataFrame] | None = {} if collect_results else None

        def _prepare_backfill_kwargs(attempt: int, batch_id: str) -> dict[str, Any]:
            """Prepare kwargs for backfiller.backfill respecting its signature.

            Some backfiller implementations (e.g., DataFetcherAutoBackfiller) accept
            additional optional keywords like `attempt` and `batch_id` for structured
            logging. Test stubs and other minimal implementations may not. To avoid
            TypeError from unexpected kwargs, inspect the callable and pass only
            supported parameters (or all if it accepts **kwargs).
            """
            func = getattr(self.backfiller, "backfill")  # type: ignore[union-attr]
            try:
                sig = inspect.signature(func)
                params: Mapping[str, inspect.Parameter] = sig.parameters
                has_var_kw = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())
            except (TypeError, ValueError):  # pragma: no cover - extremely defensive
                # If inspection fails, fall back to the minimal set guaranteed by Protocol
                params = MappingProxyType({})
                has_var_kw = False

            def _supports(name: str) -> bool:
                return has_var_kw or name in params

            kwargs: dict[str, Any] = {
                "node_id": node_id,
                "interval": interval,
            }
            if _supports("target_storage"):
                kwargs["target_storage"] = target_storage
            if _supports("attempt"):
                kwargs["attempt"] = attempt
            if _supports("batch_id"):
                kwargs["batch_id"] = batch_id
            return kwargs

        async def _chunk_worker(index: int, chunk_start: int, chunk_end: int) -> None:
            attempt = 0
            batch_id = f"{node_id}:{interval}:{chunk_start}:{chunk_end}"
            while True:
                current_attempt = attempt + 1
                try:
                    kwargs = _prepare_backfill_kwargs(current_attempt, batch_id)
                    coro = self.backfiller.backfill(  # type: ignore[union-attr]
                        chunk_start,
                        chunk_end,
                        **kwargs,
                    )
                    if sla_tracker is not None:
                        frame = await sla_tracker.observe_async(
                            "backfill_wait",
                            sla_tracker.policy.max_wait_backfill_ms,
                            coro,
                        )
                    else:
                        frame = await coro
                    if collect_results and results is not None:
                        results[index] = frame
                    return
                except Exception as exc:
                    if current_attempt >= max_attempts:
                        raise
                    attempt = current_attempt
                    sdk_metrics.observe_backfill_retry(node_id, interval)
                    logger.warning(
                        "seamless.backfill.retry",
                        extra={
                            "node_id": node_id,
                            "interval": interval,
                            "start": chunk_start,
                            "end": chunk_end,
                            "batch_id": batch_id,
                            "attempt": current_attempt,
                            "error": str(exc),
                        },
                    )
                    delay = base_delay * (2 ** (attempt - 1))
                    if jitter_enabled:
                        delay += random.uniform(0.0, delay * jitter_ratio)
                    if delay > 0:
                        await asyncio.sleep(delay)

        async def _guarded_worker(idx: int, chunk: tuple[int, int]) -> None:
            async with semaphore:
                await _chunk_worker(idx, chunk[0], chunk[1])

        async with TaskGroup() as tg:
            for idx, chunk in enumerate(chunks):
                tg.create_task(_guarded_worker(idx, chunk))

        if not collect_results or results is None:
            return []
        return [results.get(i, pd.DataFrame()) for i in range(len(chunks))]

    async def _execute_backfill_range(
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
        if not self.backfiller:
            return []
        chunks = self._chunk_backfill_ranges(start, end, interval)
        sdk_metrics.observe_backfill_start(node_id, interval)
        gap_started = time.monotonic()
        try:
            frames = await self._run_backfill_chunks(
                chunks,
                node_id=node_id,
                interval=interval,
                target_storage=target_storage,
                sla_tracker=sla_tracker,
                collect_results=collect_results,
            )
        except (Exception, ExceptionGroup):
            sdk_metrics.observe_backfill_failure(node_id, interval)
            raise
        repair_duration_ms = (time.monotonic() - gap_started) * 1000.0
        sdk_metrics.observe_gap_repair_latency(
            node_id=node_id,
            interval=interval,
            duration_ms=repair_duration_ms,
        )
        sdk_metrics.observe_backfill_complete(node_id, interval, end)
        return frames


    # ------------------------------------------------------------------
    def _normalize_world_id(self, value: Any | None) -> str:
        text = normalize_context_value(value)
        return text or ""

    def _normalize_domain(self, value: Any | None) -> str:
        text = normalize_context_value(value)
        if not text:
            return ""
        return text.lower()

    def _normalize_as_of(self, value: Any | None) -> str | None:
        text = normalize_context_value(value)
        return text or None

    def _normalize_float(self, value: Any | None) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _normalize_mapping_value(self, mapping: Mapping[str, Any], key: str) -> Any | None:
        if key in mapping:
            return mapping[key]
        if key in {"world_id", "world"}:
            for candidate in ("world_id", "world"):
                if candidate in mapping:
                    return mapping[candidate]
        return None

    def _extract_context(
        self,
        *,
        compute_context: Any | None,
        world_id: Any | None,
        execution_domain: Any | None,
        as_of: Any | None,
        min_coverage: Any | None,
        max_lag_seconds: Any | None,
    ) -> _RequestContext:
        source = self._resolve_context_source(compute_context)
        (
            world_id,
            execution_domain,
            as_of,
            min_coverage,
            max_lag_seconds,
        ) = self._merge_context_values(
            source=source,
            world_id=world_id,
            execution_domain=execution_domain,
            as_of=as_of,
            min_coverage=min_coverage,
            max_lag_seconds=max_lag_seconds,
        )

        normalized_world = self._normalize_world_id(world_id)
        normalized_domain = self._normalize_domain(execution_domain)
        normalized_as_of = self._normalize_as_of(as_of)
        normalized_min_cov = self._normalize_float(min_coverage)
        normalized_max_lag = self._normalize_float(max_lag_seconds)

        return _RequestContext(
            world_id=normalized_world,
            execution_domain=normalized_domain,
            requested_as_of=normalized_as_of,
            min_coverage=normalized_min_cov,
            max_lag_seconds=normalized_max_lag,
        )

    def _resolve_context_source(self, compute_context: Any | None) -> Any | None:
        if compute_context is None:
            return None
        if hasattr(compute_context, "context"):
            return getattr(compute_context, "context")
        return compute_context

    def _merge_context_values(
        self,
        *,
        source: Any | None,
        world_id: Any | None,
        execution_domain: Any | None,
        as_of: Any | None,
        min_coverage: Any | None,
        max_lag_seconds: Any | None,
    ) -> tuple[Any | None, Any | None, Any | None, Any | None, Any | None]:
        if isinstance(source, Mapping):
            return self._merge_mapping_context(
                source,
                world_id=world_id,
                execution_domain=execution_domain,
                as_of=as_of,
                min_coverage=min_coverage,
                max_lag_seconds=max_lag_seconds,
            )
        if source is not None:
            return self._merge_object_context(
                source,
                world_id=world_id,
                execution_domain=execution_domain,
                as_of=as_of,
                min_coverage=min_coverage,
                max_lag_seconds=max_lag_seconds,
            )
        return world_id, execution_domain, as_of, min_coverage, max_lag_seconds

    def _merge_mapping_context(
        self,
        source: Mapping[str, Any],
        *,
        world_id: Any | None,
        execution_domain: Any | None,
        as_of: Any | None,
        min_coverage: Any | None,
        max_lag_seconds: Any | None,
    ) -> tuple[Any | None, Any | None, Any | None, Any | None, Any | None]:
        world_id = world_id or self._normalize_mapping_value(source, "world_id")
        execution_domain = execution_domain or self._normalize_mapping_value(
            source, "execution_domain"
        )
        if as_of is None:
            as_of = source.get("as_of")
        if min_coverage is None:
            min_coverage = source.get("min_coverage")
        if max_lag_seconds is None:
            max_lag_seconds = source.get("max_lag") or source.get("max_lag_seconds")
        return world_id, execution_domain, as_of, min_coverage, max_lag_seconds

    def _merge_object_context(
        self,
        source: Any,
        *,
        world_id: Any | None,
        execution_domain: Any | None,
        as_of: Any | None,
        min_coverage: Any | None,
        max_lag_seconds: Any | None,
    ) -> tuple[Any | None, Any | None, Any | None, Any | None, Any | None]:
        world_id = world_id or getattr(source, "world_id", None)
        execution_domain = execution_domain or getattr(source, "execution_domain", None)
        if as_of is None:
            as_of = getattr(source, "as_of", None)
        if min_coverage is None:
            min_coverage = getattr(source, "min_coverage", None)
        if max_lag_seconds is None:
            max_lag_seconds = (
                getattr(source, "max_lag", None)
                if hasattr(source, "max_lag")
                else getattr(source, "max_lag_seconds", None)
            )
        return world_id, execution_domain, as_of, min_coverage, max_lag_seconds

    def _cache_key(
        self,
        *,
        node_id: str,
        start: int,
        end: int,
        interval: int,
        context: _RequestContext,
    ) -> str:
        world, req_as_of = context.key_components()
        values = {
            "node_id": node_id,
            "start": int(start),
            "end": int(end),
            "interval": int(interval),
            "conformance_version": CONFORMANCE_VERSION,
            "world_id": world,
            "as_of": req_as_of,
            "execution_domain": context.execution_domain,
        }
        try:
            return self._cache_key_template.format(**values)
        except Exception:
            return (
                f"{node_id}:{int(start)}:{int(end)}:{int(interval)}:"
                f"{CONFORMANCE_VERSION}:{world}:{req_as_of}"
            )

    def _backfill_key(
        self,
        *,
        node_id: str,
        interval: int,
        start: int,
        end: int,
        context: _RequestContext | None = None,
    ) -> str:
        world = ""
        requested_as_of = ""
        if context is not None:
            world, requested_as_of = context.key_components()
        return (
            f"{node_id}:{int(interval)}:{int(start)}:{int(end)}:"
            f"{world}:{requested_as_of}"
        )

    def _parse_as_of_value(self, value: str) -> tuple[bool, Any]:
        text = value.strip()
        if not text:
            return False, None
        if text.isdigit():
            try:
                return True, int(text)
            except ValueError:
                try:
                    return True, float(text)
                except ValueError:
                    return False, None
        try:
            normalized = text.replace("Z", "+00:00")
            return True, datetime.fromisoformat(normalized)
        except ValueError:
            return False, None

    def _compare_as_of(self, left: str, right: str) -> int:
        success_left, parsed_left = self._parse_as_of_value(left)
        success_right, parsed_right = self._parse_as_of_value(right)
        if success_left and success_right:
            if parsed_left < parsed_right:
                return -1
            if parsed_left > parsed_right:
                return 1
            return 0
        if left < right:
            return -1
        if left > right:
            return 1
        return 0

    def _merge_decisions(
        self,
        base: _DowngradeDecision | None,
        new: _DowngradeDecision | None,
    ) -> _DowngradeDecision | None:
        if new is None:
            return base
        if base is None:
            return new
        severity = {SLAViolationMode.PARTIAL_FILL: 0, SLAViolationMode.HOLD: 1}
        base_severity = severity.get(base.mode, 0)
        new_severity = severity.get(new.mode, 0)
        if new_severity > base_severity:
            return new
        if new_severity < base_severity:
            return base
        # Prefer the most recent reason but keep richer metrics if present
        coverage = new.coverage_ratio if new.coverage_ratio is not None else base.coverage_ratio
        staleness = new.staleness_ms if new.staleness_ms is not None else base.staleness_ms
        violation = base.violation or new.violation
        return _DowngradeDecision(
            mode=base.mode,
            reason=new.reason or base.reason,
            violation=violation,
            coverage_ratio=coverage,
            staleness_ms=staleness,
        )

    def _domain_gate(
        self,
        context: _RequestContext,
        metadata: SeamlessFetchMetadata,
        *,
        node_id: str,
        interval: int,
    ) -> _DowngradeDecision | None:
        return self._domain_gate_evaluator.evaluate(
            context,
            metadata,
            node_id=node_id,
            interval=interval,
        )

    async def fetch(
        self,
        start: int,
        end: int,
        *,
        node_id: str,
        interval: int,
        compute_context: Any | None = None,
        world_id: Any | None = None,
        execution_domain: Any | None = None,
        as_of: Any | None = None,
        min_coverage: Any | None = None,
        max_lag_seconds: Any | None = None,
    ) -> SeamlessFetchResult:
        """
        Fetch data transparently from available sources while enforcing domain policies.
        """

        self._validate_node_id(node_id)
        self._last_conformance_report = None
        self._last_fetch_metadata = None

        context = self._extract_context(
            compute_context=compute_context,
            world_id=world_id,
            execution_domain=execution_domain,
            as_of=as_of,
            min_coverage=min_coverage,
            max_lag_seconds=max_lag_seconds,
        )
        cache_key = self._cache_key(
            node_id=node_id, start=start, end=end, interval=interval, context=context
        )

        self._enforce_as_of_requirement(
            node_id=node_id,
            interval=interval,
            context=context,
        )

        tracker = self._build_sla_tracker(node_id, interval)

        response, cache_hit = self._maybe_get_cached_response(
            cache_key,
            context,
            node_id=node_id,
            interval=interval,
        )

        if response is None:
            result = await self._dispatch_fetch_strategy(
                start,
                end,
                node_id=node_id,
                interval=interval,
                tracker=tracker,
                context=context,
            )
            response = await self._finalize_response(
                result,
                start=start,
                end=end,
                node_id=node_id,
                interval=interval,
                request_context=context,
                cache_key=cache_key,
            )

        self._apply_sla_and_domain(
            tracker=tracker,
            context=context,
            response=response,
            node_id=node_id,
            interval=interval,
        )

        self._record_fingerprint(
            node_id,
            interval,
            response.metadata.dataset_fingerprint,
            context,
        )

        self._maybe_store_in_cache(
            cache_key,
            response,
            context=context,
            cache_hit=cache_hit,
        )

        # Preserve metadata on the returned frame for callers expecting attributes.
        response.frame.metadata = response.metadata  # type: ignore[attr-defined]
        return response
    
    async def coverage(
        self, *, node_id: str, interval: int
    ) -> list[tuple[int, int]]:
        """Return combined coverage from all sources."""
        self._validate_node_id(node_id)
        all_ranges: list[tuple[int, int]] = []
        
        # Collect coverage from all available sources
        for source in self._get_ordered_sources():
            try:
                ranges = await source.coverage(node_id=node_id, interval=interval)
                all_ranges.extend(ranges)
            except Exception as exc:
                if isinstance(exc, SeamlessSLAExceeded):
                    raise
                continue  # Skip failed sources
        
        # Merge overlapping ranges with interval-aware semantics
        try:
            merged = _merge_coverage(all_ranges, interval)
            return [(r.start, r.end) for r in merged]
        except Exception:
            # Fallback to simple merge if utilities are unavailable
            return self._merge_ranges(all_ranges)

    async def fill_missing(
        self,
        start: int,
        end: int,
        *,
        node_id: str,
        interval: int,
    ) -> None:
        """Bridge ``HistoryProvider`` gap-filling to Seamless backfill.

        This method reuses :meth:`ensure_data_available` to populate missing
        ranges so that :class:`HistoryWarmupService` and
        :class:`HistoryWarmupPoller` can treat Seamless providers as standard
        history sources.
        """

        await self.ensure_data_available(
            start,
            end,
            node_id=node_id,
            interval=interval,
        )

    async def ensure_data_available(
        self,
        start: int,
        end: int,
        *,
        node_id: str,
        interval: int,
        sla_tracker: "_SLATracker | None" = None,
        request_context: _RequestContext | None = None,
    ) -> bool:
        """Ensure data is available for the requested range."""
        self._validate_node_id(node_id)
        tracker = sla_tracker or self._build_sla_tracker(node_id, interval)
        pipeline = _AvailabilityPipeline(
            provider=self,
            tracker=tracker,
            request_context=request_context,
        )
        return await pipeline.ensure(
            start,
            end,
            node_id=node_id,
            interval=interval,
        )
    
    def _get_ordered_sources(self) -> list[DataSource]:
        """Get data sources in priority order."""
        sources = []
        if self.cache_source:
            sources.append(self.cache_source)
        if self.storage_source:
            sources.append(self.storage_source)
        return sorted(sources, key=lambda s: s.priority.value)

    def _enforce_as_of_requirement(
        self,
        *,
        node_id: str,
        interval: int,
        context: _RequestContext,
    ) -> None:
        if context.execution_domain in {"backtest", "dryrun"} and context.requested_as_of is None:
            logger.error(
                "seamless.domain_gate.missing_as_of",
                extra={
                    "node_id": node_id,
                    "interval": interval,
                    "execution_domain": context.execution_domain,
                    "world_id": context.world_id,
                },
            )
            raise SeamlessDomainPolicyError(
                "as_of is required for backtest/dryrun domains"
            )

    def _maybe_get_cached_response(
        self,
        cache_key: str,
        context: _RequestContext,
        *,
        node_id: str,
        interval: int,
    ) -> tuple[SeamlessFetchResult | None, bool]:
        if not self._cache_available():
            return None, False
        cached_entry = self._cache_lookup(
            cache_key,
            node_id=node_id,
            interval=int(interval),
            world_id=context.world_id or None,
        )
        if cached_entry is None:
            return None, False
        response = self._materialize_cached_result(cached_entry)
        return response, True

    async def _dispatch_fetch_strategy(
        self,
        start: int,
        end: int,
        *,
        node_id: str,
        interval: int,
        tracker: "_SLATracker | None",
        context: _RequestContext,
    ) -> pd.DataFrame:
        if self.strategy == DataAvailabilityStrategy.FAIL_FAST:
            return await self._fetch_fail_fast(
                start,
                end,
                node_id=node_id,
                interval=interval,
                sla_tracker=tracker,
                request_context=context,
            )
        if self.strategy == DataAvailabilityStrategy.AUTO_BACKFILL:
            return await self._fetch_auto_backfill(
                start,
                end,
                node_id=node_id,
                interval=interval,
                sla_tracker=tracker,
                request_context=context,
            )
        if self.strategy == DataAvailabilityStrategy.PARTIAL_FILL:
            return await self._fetch_partial_fill(
                start,
                end,
                node_id=node_id,
                interval=interval,
                sla_tracker=tracker,
                request_context=context,
            )
        return await self._fetch_seamless(
            start,
            end,
            node_id=node_id,
            interval=interval,
            sla_tracker=tracker,
            request_context=context,
        )

    def _apply_sla_and_domain(
        self,
        *,
        tracker: "_SLATracker | None",
        context: _RequestContext,
        response: SeamlessFetchResult,
        node_id: str,
        interval: int,
    ) -> None:
        downgrade: _DowngradeDecision | None = None
        if tracker:
            tracker.observe_total()
            downgrade = self._resolve_downgrade(tracker, response.metadata)

        domain_decision = self._domain_gate(
            context,
            response.metadata,
            node_id=node_id,
            interval=interval,
        )
        final_decision = self._merge_decisions(downgrade, domain_decision)

        if final_decision:
            self._apply_downgrade(
                response,
                final_decision,
                node_id=node_id,
                interval=interval,
            )

    def _maybe_store_in_cache(
        self,
        cache_key: str,
        response: SeamlessFetchResult,
        *,
        context: _RequestContext,
        cache_hit: bool,
    ) -> None:
        if not self._cache_available() or cache_hit:
            return
        self._cache_snapshot(
            cache_key,
            response,
            world_id=context.world_id or None,
        )
    
    async def _fetch_seamless(
        self,
        start: int,
        end: int,
        *,
        node_id: str,
        interval: int,
        sla_tracker: "_SLATracker | None" = None,
        request_context: _RequestContext | None = None,
    ) -> pd.DataFrame:
        """Implement seamless fetching strategy."""
        self._last_conformance_report = None
        planner = _SeamlessFetchPlanner(
            provider=self,
            node_id=node_id,
            interval=interval,
            tracker=sla_tracker,
            request_context=request_context,
        )
        return await planner.fetch(start, end)
    
    async def _fetch_fail_fast(
        self,
        start: int,
        end: int,
        *,
        node_id: str,
        interval: int,
        sla_tracker: "_SLATracker | None" = None,
        request_context: _RequestContext | None = None,
    ) -> pd.DataFrame:
        """Fail fast strategy - only use existing data."""
        for source in self._get_ordered_sources():
            try:
                available = await source.is_available(
                    start, end, node_id=node_id, interval=interval
                )
                if available:
                    fetch_coro = source.fetch(start, end, node_id=node_id, interval=interval)
                    if sla_tracker and source.priority == DataSourcePriority.STORAGE:
                        return await sla_tracker.observe_async(
                            "storage_wait",
                            sla_tracker.policy.max_wait_storage_ms,
                            fetch_coro,
                        )
                    return await fetch_coro
            except Exception as exc:
                if isinstance(exc, SeamlessSLAExceeded):
                    raise
                continue
        
        raise RuntimeError(f"No data available for range [{start}, {end}] in fail-fast mode")
    
    async def _fetch_auto_backfill(
        self,
        start: int,
        end: int,
        *,
        node_id: str,
        interval: int,
        sla_tracker: "_SLATracker | None" = None,
        request_context: _RequestContext | None = None,
    ) -> pd.DataFrame:
        """Auto-backfill strategy - ensure data is backfilled before returning."""
        await self.ensure_data_available(
            start,
            end,
            node_id=node_id,
            interval=interval,
            sla_tracker=sla_tracker,
            request_context=request_context,
        )
        return await self._fetch_seamless(
            start,
            end,
            node_id=node_id,
            interval=interval,
            sla_tracker=sla_tracker,
            request_context=request_context,
        )
    
    async def _fetch_partial_fill(
        self,
        start: int,
        end: int,
        *,
        node_id: str,
        interval: int,
        sla_tracker: "_SLATracker | None" = None,
        request_context: _RequestContext | None = None,
    ) -> pd.DataFrame:
        """Partial fill strategy - return what's available, backfill in background."""
        # Start background backfill but don't wait
        if self.backfiller:
            await self._start_background_backfill(
                start,
                end,
                node_id=node_id,
                interval=interval,
                request_context=request_context,
            )

        # Return what's currently available
        return await self._fetch_seamless(
            start,
            end,
            node_id=node_id,
            interval=interval,
            sla_tracker=sla_tracker,
            request_context=request_context,
        )

    # ------------------------------------------------------------------
    async def _finalize_response(
        self,
        frame: pd.DataFrame,
        *,
        start: int,
        end: int,
        node_id: str,
        interval: int,
        request_context: _RequestContext | None = None,
        cache_key: str | None = None,
    ) -> SeamlessFetchResult:

        (
            world_id,
            execution_domain,
            requested_as_of,
        ) = self._extract_request_details(request_context)

        if frame.empty:
            self._last_conformance_report = None
            return self._build_empty_result(
                frame,
                node_id=node_id,
                interval=interval,
                start=start,
                end=end,
                world_id=world_id,
                execution_domain=execution_domain,
                requested_as_of=requested_as_of,
                cache_key=cache_key,
                report=None,
            )

        normalized, report = self._normalize_with_conformance(frame, interval)
        self._last_conformance_report = report
        self._record_conformance_metrics(report, node_id=node_id, interval=interval)

        if self._should_fail_conformance(report):
            raise ConformancePipelineError(report)

        stabilized = self._stabilize_frame(normalized)
        if stabilized.empty:
            return self._build_empty_result(
                stabilized,
                node_id=node_id,
                interval=interval,
                start=start,
                end=end,
                world_id=world_id,
                execution_domain=execution_domain,
                requested_as_of=requested_as_of,
                cache_key=cache_key,
                report=report,
            )

        coverage_bounds = self._coverage_bounds(stabilized)
        canonical_metadata = {
            "node_id": node_id,
            "interval": int(interval),
            "coverage_bounds": coverage_bounds,
            "conformance_version": CONFORMANCE_VERSION,
        }
        legacy_metadata = {
            **canonical_metadata,
            "requested_bounds": (int(start), int(end)),
        }

        publication_ctx = await self._handle_artifact_publication(
            stabilized,
            report,
            start=start,
            end=end,
            node_id=node_id,
            interval=interval,
            coverage_bounds=coverage_bounds,
            canonical_metadata=canonical_metadata,
            legacy_metadata=legacy_metadata,
        )

        metadata = SeamlessFetchMetadata(
            node_id=node_id,
            interval=int(interval),
            requested_range=(int(start), int(end)),
            rows=int(len(stabilized)),
            coverage_bounds=publication_ctx.coverage_bounds,
            conformance_flags=dict(report.flags_counts),
            conformance_warnings=report.warnings,
            conformance_version=CONFORMANCE_VERSION,
            dataset_fingerprint=publication_ctx.fingerprint,
            as_of=publication_ctx.as_of,
            manifest_uri=publication_ctx.manifest_uri,
            artifact=publication_ctx.publication,
            world_id=world_id,
            execution_domain=execution_domain,
            requested_as_of=requested_as_of,
            cache_key=cache_key,
        )

        self._finalize_metadata_metrics(metadata, node_id=node_id, interval=interval)
        self._sync_metadata_attrs(stabilized, metadata)
        self._last_fetch_metadata = metadata
        return SeamlessFetchResult(stabilized, metadata)

    @staticmethod
    def _extract_request_details(
        request_context: _RequestContext | None,
    ) -> tuple[str | None, str | None, str | None]:
        if request_context is None:
            return None, None, None
        return (
            request_context.world_id or None,
            request_context.execution_domain or None,
            request_context.requested_as_of,
        )

    def _build_empty_result(
        self,
        frame: pd.DataFrame,
        *,
        node_id: str,
        interval: int,
        start: int,
        end: int,
        world_id: str | None,
        execution_domain: str | None,
        requested_as_of: str | None,
        cache_key: str | None,
        report: ConformanceReport | None,
    ) -> SeamlessFetchResult:
        metadata = SeamlessFetchMetadata(
            node_id=node_id,
            interval=int(interval),
            requested_range=(int(start), int(end)),
            rows=0,
            coverage_bounds=None,
            conformance_flags=dict(report.flags_counts) if report else {},
            conformance_warnings=report.warnings if report else (),
            conformance_version=CONFORMANCE_VERSION,
            dataset_fingerprint=None,
            as_of=None,
            manifest_uri=None,
            artifact=None,
            world_id=world_id,
            execution_domain=execution_domain,
            requested_as_of=requested_as_of,
            cache_key=cache_key,
        )
        self._sync_metadata_attrs(frame, metadata)
        return SeamlessFetchResult(frame, metadata)

    def _normalize_with_conformance(
        self, frame: pd.DataFrame, interval: int
    ) -> tuple[pd.DataFrame, ConformanceReport]:
        if not self._conformance:
            return frame.copy(), ConformanceReport()
        try:
            interval_override = self._conformance_interval or interval
            normalized, report = self._conformance.normalize(
                frame,
                schema=self._conformance_schema,
                interval=interval_override,
            )
            return normalized, report
        except ConformancePipelineError:
            raise
        except Exception:  # pragma: no cover - defensive guard
            return frame.copy(), ConformanceReport()

    def _record_conformance_metrics(
        self, report: ConformanceReport, *, node_id: str, interval: int
    ) -> None:
        if not self._conformance:
            return
        try:
            sdk_metrics.observe_conformance_report(
                node_id=node_id,
                interval=interval,
                flags=report.flags_counts,
                warnings=report.warnings,
            )
        except Exception:  # pragma: no cover - best effort metrics
            pass

    def _should_fail_conformance(self, report: ConformanceReport) -> bool:
        if self._partial_ok:
            return False
        return bool(report.warnings or report.flags_counts)

    def _compute_initial_fingerprints(
        self,
        stabilized: pd.DataFrame,
        *,
        canonical_metadata: Mapping[str, Any],
        legacy_metadata: Mapping[str, Any],
    ) -> tuple[str | None, str | None]:
        fingerprint: str | None = None
        preview_fingerprint: str | None = None
        should_compute_immediate = (
            not self._publish_fingerprint or self._registrar is None
        )
        if should_compute_immediate:
            fingerprint = self._compute_fingerprint_value(
                stabilized,
                canonical_metadata=canonical_metadata,
                legacy_metadata=legacy_metadata,
                mode=self._fingerprint_mode,
            )
        elif self._preview_fingerprint:
            preview_fingerprint = self._compute_fingerprint_value(
                stabilized,
                canonical_metadata=canonical_metadata,
                legacy_metadata=legacy_metadata,
                mode=_FINGERPRINT_MODE_CANONICAL,
            )
        return fingerprint, preview_fingerprint

    def _build_publish_call(
        self,
        *,
        stabilized: pd.DataFrame,
        report: ConformanceReport,
        start: int,
        end: int,
        node_id: str,
        interval: int,
        coverage_bounds: tuple[int, int] | None,
        canonical_metadata: Mapping[str, Any],
        legacy_metadata: Mapping[str, Any],
        fingerprint: str | None,
        as_of: str,
    ) -> tuple[Any | None, str | None]:
        publish_call: Any | None = None
        try:
            publish_call = self._registrar.publish(  # type: ignore[union-attr]
                stabilized,
                node_id=node_id,
                interval=interval,
                conformance_report=report,
                requested_range=(int(start), int(end)),
                publish_fingerprint=self._publish_fingerprint,
                early_fingerprint=self._early_fingerprint,
            )
        except TypeError:
            if coverage_bounds is not None:
                try:
                    if fingerprint is None:
                        fingerprint = self._compute_fingerprint_value(
                            stabilized,
                            canonical_metadata=canonical_metadata,
                            legacy_metadata=legacy_metadata,
                            mode=self._fingerprint_mode,
                        )
                    publish_call = self._registrar.publish(  # type: ignore[misc,union-attr]
                        stabilized,
                        node_id=node_id,
                        interval=interval,
                        coverage_bounds=coverage_bounds,
                        fingerprint=fingerprint,
                        as_of=as_of,
                        conformance_flags=report.flags_counts,
                        conformance_warnings=report.warnings,
                        request_window=(int(start), int(end)),
                        publish_fingerprint=self._publish_fingerprint,
                        early_fingerprint=self._early_fingerprint,
                    )
                except Exception:  # pragma: no cover - publication failures shouldn't crash
                    publish_call = None
        except Exception:  # pragma: no cover - publication failures shouldn't crash
            publish_call = None
        return publish_call, fingerprint

    async def _execute_publish_call(
        self,
        publish_call: Any | None,
        *,
        node_id: str,
        interval: int,
    ) -> ArtifactPublication | None:
        if publish_call is None:
            return None
        try:
            start_time = time.monotonic()
            if inspect.isawaitable(publish_call):
                publication = await publish_call
            else:
                publication = publish_call
        except Exception:  # pragma: no cover - publication failures shouldn't crash
            return None
        if self._publish_fingerprint:
            elapsed_ms = (time.monotonic() - start_time) * 1000.0
            sdk_metrics.observe_artifact_publish_latency(
                node_id=node_id,
                interval=interval,
                duration_ms=elapsed_ms,
            )
        return publication

    async def _handle_artifact_publication(
        self,
        stabilized: pd.DataFrame,
        report: ConformanceReport,
        *,
        start: int,
        end: int,
        node_id: str,
        interval: int,
        coverage_bounds: tuple[int, int] | None,
        canonical_metadata: Mapping[str, Any],
        legacy_metadata: Mapping[str, Any],
    ) -> _PublicationContext:
        fingerprint, preview_fingerprint = self._compute_initial_fingerprints(
            stabilized,
            canonical_metadata=canonical_metadata,
            legacy_metadata=legacy_metadata,
        )
        as_of = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        manifest_uri: str | None = None
        publication: ArtifactPublication | None = None
        approx_bytes = (
            int(stabilized.memory_usage(deep=True).sum()) if not stabilized.empty else 0
        )

        if self._registrar:
            publish_call, fingerprint = self._build_publish_call(
                stabilized=stabilized,
                report=report,
                start=start,
                end=end,
                node_id=node_id,
                interval=interval,
                coverage_bounds=coverage_bounds,
                canonical_metadata=canonical_metadata,
                legacy_metadata=legacy_metadata,
                fingerprint=fingerprint,
                as_of=as_of,
            )
            publication = await self._execute_publish_call(
                publish_call,
                node_id=node_id,
                interval=interval,
            )

        if publication:
            (
                publication_fingerprint,
                coverage_bounds,
                manifest_uri,
                as_of,
            ) = self._normalize_publication(
                publication,
                stabilized,
                coverage_bounds,
                canonical_metadata,
                legacy_metadata,
                fingerprint,
                preview_fingerprint,
                node_id=node_id,
                interval=interval,
                approx_bytes=approx_bytes,
                as_of_ref=as_of,
            )
            if publication_fingerprint is not None:
                fingerprint = publication_fingerprint

        if fingerprint is None:
            fingerprint = self._compute_fingerprint_value(
                stabilized,
                canonical_metadata=canonical_metadata,
                legacy_metadata=legacy_metadata,
                mode=self._fingerprint_mode,
            )

        return _PublicationContext(
            fingerprint=fingerprint,
            coverage_bounds=coverage_bounds,
            manifest_uri=manifest_uri,
            publication=publication,
            as_of=as_of,
        )

    def _normalize_publication(
        self,
        publication: ArtifactPublication,
        stabilized: pd.DataFrame,
        coverage_bounds: tuple[int, int] | None,
        canonical_metadata: Mapping[str, Any],
        legacy_metadata: Mapping[str, Any],
        fingerprint: str | None,
        preview_fingerprint: str | None,
        *,
        node_id: str,
        interval: int,
        approx_bytes: int,
        as_of_ref: str,
        ) -> tuple[str | None, tuple[int, int] | None, str | None, str]:
        pub_fingerprint = getattr(publication, "dataset_fingerprint", None)
        manifest_uri: str | None = getattr(publication, "manifest_uri", None)
        as_of = getattr(publication, "as_of", as_of_ref)
        if isinstance(pub_fingerprint, str):
            fingerprint = self._resolve_publication_fingerprint(
                publication,
                pub_fingerprint,
                stabilized,
                canonical_metadata,
                legacy_metadata,
                fingerprint,
                preview_fingerprint,
            )
        if hasattr(publication, "start") and hasattr(publication, "end"):
            coverage_bounds = (
                int(getattr(publication, "start")),
                int(getattr(publication, "end")),
            )
        elif hasattr(publication, "coverage_bounds"):
            bounds = getattr(publication, "coverage_bounds")
            if isinstance(bounds, tuple) and len(bounds) == 2:
                coverage_bounds = (int(bounds[0]), int(bounds[1]))
        self._record_artifact_bytes(
            node_id=node_id,
            interval=interval,
            approx_bytes=approx_bytes,
            publication=publication,
        )
        return fingerprint, coverage_bounds, manifest_uri, as_of

    def _resolve_publication_fingerprint(
        self,
        publication: ArtifactPublication,
        pub_fingerprint: str,
        stabilized: pd.DataFrame,
        canonical_metadata: Mapping[str, Any],
        legacy_metadata: Mapping[str, Any],
        fingerprint: str | None,
        preview_fingerprint: str | None,
    ) -> str | None:
        (
            normalized_fp,
            canonical_for_preview,
            fingerprint,
        ) = self._resolve_effective_publication_fingerprint(
            pub_fingerprint=pub_fingerprint,
            stabilized=stabilized,
            canonical_metadata=canonical_metadata,
            legacy_metadata=legacy_metadata,
            fingerprint=fingerprint,
        )
        self._update_publication_manifest(
            publication,
            normalized_fp=normalized_fp,
            canonical_for_preview=canonical_for_preview,
            preview_fingerprint=preview_fingerprint,
        )
        return fingerprint

    @staticmethod
    def _looks_like_raw_sha256(value: str) -> bool:
        return len(value) == 64 and all(ch in "0123456789abcdefABCDEF" for ch in value)

    def _resolve_effective_publication_fingerprint(
        self,
        *,
        pub_fingerprint: str,
        stabilized: pd.DataFrame,
        canonical_metadata: Mapping[str, Any],
        legacy_metadata: Mapping[str, Any],
        fingerprint: str | None,
    ) -> tuple[str, str | None, str | None]:
        normalized_fp = pub_fingerprint
        canonical_normalized: str | None = None
        if normalized_fp.startswith("lake:sha256:"):
            canonical_normalized = normalized_fp.replace("lake:", "", 1)
        elif normalized_fp.startswith("sha256:"):
            canonical_normalized = normalized_fp.lower()
        elif self._looks_like_raw_sha256(normalized_fp):
            canonical_normalized = f"sha256:{normalized_fp.lower()}"

        if self._fingerprint_mode == _FINGERPRINT_MODE_LEGACY:
            if fingerprint is None:
                fingerprint = self._compute_fingerprint_value(
                    stabilized,
                    canonical_metadata=canonical_metadata,
                    legacy_metadata=legacy_metadata,
                    mode=_FINGERPRINT_MODE_LEGACY,
                )
            normalized_fp = fingerprint
        else:
            if canonical_normalized:
                normalized_fp = canonical_normalized
            fingerprint = normalized_fp

        canonical_for_preview = canonical_normalized
        if (
            canonical_for_preview is None
            and self._fingerprint_mode == _FINGERPRINT_MODE_LEGACY
        ):
            canonical_for_preview = self._compute_fingerprint_value(
                stabilized,
                canonical_metadata=canonical_metadata,
                legacy_metadata=legacy_metadata,
                mode=_FINGERPRINT_MODE_CANONICAL,
            )

        return normalized_fp, canonical_for_preview, fingerprint

    def _update_publication_manifest(
        self,
        publication: ArtifactPublication,
        *,
        normalized_fp: str,
        canonical_for_preview: str | None,
        preview_fingerprint: str | None,
    ) -> None:
        manifest_obj = getattr(publication, "manifest", None)
        if isinstance(manifest_obj, dict):
            manifest_obj["dataset_fingerprint"] = normalized_fp
        if (
            preview_fingerprint
            and canonical_for_preview
            and canonical_for_preview != preview_fingerprint
        ):
            logger.warning(
                "seamless.fingerprint.preview_mismatch",
                canonical=canonical_for_preview,
                preview=preview_fingerprint,
            )
        try:
            publication.dataset_fingerprint = normalized_fp  # type: ignore[misc]
        except Exception:  # pragma: no cover - defensive guard
            pass

    def _record_artifact_bytes(
        self,
        *,
        node_id: str,
        interval: int,
        approx_bytes: int,
        publication: ArtifactPublication,
    ) -> None:
        bytes_written = approx_bytes
        data_uri = getattr(publication, "uri", None) or getattr(
            publication, "data_uri", None
        )
        if data_uri:
            try:
                bytes_written = max(bytes_written, int(os.path.getsize(data_uri)))
            except OSError:
                pass
        if bytes_written > 0:
            sdk_metrics.observe_artifact_bytes_written(
                node_id=node_id,
                interval=interval,
                bytes_written=bytes_written,
            )

    def _finalize_metadata_metrics(
        self, metadata: SeamlessFetchMetadata, *, node_id: str, interval: int
    ) -> None:
        metadata.coverage_ratio = self._compute_coverage_ratio(metadata)
        metadata.staleness_ms = self._compute_staleness_ms(metadata)
        sdk_metrics.observe_coverage_ratio(
            node_id=node_id,
            interval=interval,
            ratio=metadata.coverage_ratio,
        )
        staleness_seconds = (
            metadata.staleness_ms / 1000.0 if metadata.staleness_ms is not None else None
        )
        sdk_metrics.observe_live_staleness(
            node_id=node_id,
            interval=interval,
            staleness_seconds=staleness_seconds,
        )

    def _sync_metadata_attrs(
        self, frame: pd.DataFrame, metadata: SeamlessFetchMetadata
    ) -> None:
        attrs = dict(frame.attrs)
        attrs.update(
            {
                "dataset_fingerprint": metadata.dataset_fingerprint,
                "as_of": metadata.as_of,
                "coverage_bounds": metadata.coverage_bounds,
                "conformance_flags": metadata.conformance_flags,
                "conformance_warnings": metadata.conformance_warnings,
                "conformance_version": metadata.conformance_version,
                "manifest_uri": metadata.manifest_uri,
                "requested_range": metadata.requested_range,
                "rows": metadata.rows,
                "downgraded": metadata.downgraded,
                "downgrade_mode": metadata.downgrade_mode,
                "downgrade_reason": metadata.downgrade_reason,
                "sla_violation": metadata.sla_violation,
                "coverage_ratio": metadata.coverage_ratio,
                "staleness_ms": metadata.staleness_ms,
                "world_id": metadata.world_id,
                "execution_domain": metadata.execution_domain,
                "requested_as_of": metadata.requested_as_of,
                "cache_key": metadata.cache_key,
            }
        )
        frame.attrs = attrs

    def _compute_coverage_ratio(
        self, metadata: SeamlessFetchMetadata
    ) -> float | None:
        start, end = metadata.requested_range
        requested_span = max(0, end - start)
        if requested_span <= 0:
            return 1.0 if metadata.rows > 0 else 0.0
        row_ratio: float | None = None
        if metadata.interval > 0:
            if metadata.rows <= 0:
                row_ratio = 0.0
            else:
                expected_rows = math.floor(requested_span / metadata.interval) + 1
                expected_rows = max(expected_rows, 1)
                row_ratio = min(1.0, metadata.rows / expected_rows)
        bounds = metadata.coverage_bounds
        bounds_ratio: float | None = None
        if bounds is not None:
            cov_start, cov_end = bounds
            overlap_start = max(start, cov_start)
            overlap_end = min(end, cov_end)
            if overlap_end > overlap_start:
                coverage_span = max(0, overlap_end - overlap_start)
                bounds_ratio = max(0.0, min(1.0, coverage_span / requested_span))
            else:
                bounds_ratio = 0.0
        ratios = [ratio for ratio in (row_ratio, bounds_ratio) if ratio is not None]
        if not ratios:
            return 0.0
        return min(ratios)

    def _compute_staleness_ms(
        self, metadata: SeamlessFetchMetadata
    ) -> float | None:
        bounds = metadata.coverage_bounds
        if bounds is None:
            return None
        _, cov_end = bounds
        now_ms = time.time() * 1000.0
        staleness = now_ms - (cov_end * 1000.0)
        return max(staleness, 0.0)

    def _resolve_downgrade(
        self, tracker: _SLATracker, metadata: SeamlessFetchMetadata
    ) -> _DowngradeDecision | None:
        if not self._sla:
            return None

        coverage_ratio = metadata.coverage_ratio
        if coverage_ratio is None:
            coverage_ratio = self._compute_coverage_ratio(metadata)
            metadata.coverage_ratio = coverage_ratio
        staleness_ms = metadata.staleness_ms
        if staleness_ms is None:
            staleness_ms = self._compute_staleness_ms(metadata)
            metadata.staleness_ms = staleness_ms
        decision = self._evaluate_sla_violation(self._sla, tracker.violation, coverage_ratio, staleness_ms)
        return decision

    @staticmethod
    def _evaluate_sla_violation(
        sla: SLAPolicy,
        violation: _SLAViolationDetail | None,
        coverage_ratio: float | None,
        staleness_ms: float | None,
    ) -> _DowngradeDecision | None:
        mode: SLAViolationMode | None = None
        reason: str | None = None
        if violation:
            mode = sla.on_violation
            reason = "sla_violation"

        if (
            sla.min_coverage is not None
            and coverage_ratio is not None
            and coverage_ratio < sla.min_coverage
        ):
            mode = SLAViolationMode.HOLD
            reason = "coverage_breach"

        if (
            sla.max_lag_seconds is not None
            and staleness_ms is not None
            and staleness_ms > sla.max_lag_seconds * 1000
        ):
            mode = SLAViolationMode.HOLD
            reason = "freshness_breach"

        if mode is None or reason is None:
            return None
        return _DowngradeDecision(
            mode=mode,
            reason=reason,
            violation=violation,
            coverage_ratio=coverage_ratio,
            staleness_ms=staleness_ms,
        )

    def _apply_downgrade(
        self,
        result: SeamlessFetchResult,
        decision: _DowngradeDecision,
        *,
        node_id: str,
        interval: int,
    ) -> None:
        metadata = result.metadata
        metadata.downgraded = True
        metadata.downgrade_mode = decision.mode.value
        metadata.downgrade_reason = decision.reason
        metadata.coverage_ratio = decision.coverage_ratio
        metadata.staleness_ms = decision.staleness_ms

        if decision.violation:
            metadata.sla_violation = {
                "phase": decision.violation.phase,
                "elapsed_ms": decision.violation.elapsed_ms,
                "budget_ms": decision.violation.budget_ms,
            }
        else:
            metadata.sla_violation = None

        self._sync_metadata_attrs(result.frame, metadata)

        violation_payload = metadata.sla_violation or {}
        logger.warning(
            "seamless.sla.downgrade",
            extra={
                "node_id": node_id,
                "interval": interval,
                "mode": metadata.downgrade_mode,
                "reason": metadata.downgrade_reason,
                "coverage_ratio": metadata.coverage_ratio,
                "staleness_ms": metadata.staleness_ms,
                "phase": violation_payload.get("phase"),
                "elapsed_ms": violation_payload.get("elapsed_ms"),
                "budget_ms": violation_payload.get("budget_ms"),
                "dataset_fingerprint": metadata.dataset_fingerprint,
                "as_of": metadata.as_of,
            },
        )

        reason = metadata.downgrade_reason or "unknown"
        if decision.mode is SLAViolationMode.HOLD:
            sdk_metrics.observe_domain_hold(
                node_id=node_id,
                interval=interval,
                reason=reason,
            )
        elif decision.mode is SLAViolationMode.PARTIAL_FILL:
            sdk_metrics.observe_partial_fill(
                node_id=node_id,
                interval=interval,
                reason=reason,
            )

    def _stabilize_frame(self, frame: pd.DataFrame) -> pd.DataFrame:
        if frame.empty:
            return frame
        if self._stabilization_bars <= 0:
            return frame.reset_index(drop=True)
        if len(frame) <= self._stabilization_bars:
            return frame.iloc[0:0].copy()
        stabilized = frame.iloc[:-self._stabilization_bars].copy()
        stabilized.reset_index(drop=True, inplace=True)
        return stabilized

    def _coverage_bounds(self, frame: pd.DataFrame) -> tuple[int, int] | None:
        if frame.empty or "ts" not in frame.columns:
            return None
        start = int(frame["ts"].iloc[0])
        end = int(frame["ts"].iloc[-1])
        return (start, end)

    def _compute_fingerprint_value(
        self,
        frame: pd.DataFrame,
        *,
        canonical_metadata: dict[str, Any],
        legacy_metadata: dict[str, Any],
        mode: str,
    ) -> str:
        if mode == _FINGERPRINT_MODE_LEGACY:
            return compute_legacy_artifact_fingerprint(frame, legacy_metadata)
        return compute_artifact_fingerprint(frame, canonical_metadata)

    def _record_fingerprint(
        self,
        node_id: str,
        interval: int,
        fingerprint: str | None,
        context: _RequestContext | None = None,
    ) -> None:
        if not fingerprint:
            return
        world = ""
        requested_as_of = ""
        if context is not None:
            world, requested_as_of = context.key_components()
        key = (str(node_id), int(interval), world, requested_as_of)
        seen = self._fingerprint_index[key]
        if fingerprint in seen:
            sdk_metrics.observe_fingerprint_collision(node_id=node_id, interval=interval)
            # Refresh recency so that duplicate fingerprints remain in the window.
            try:
                seen.remove(fingerprint)
            except ValueError:  # pragma: no cover - defensive guard
                pass
        seen.append(fingerprint)

    async def _start_background_backfill(
        self,
        start: int,
        end: int,
        *,
        node_id: str,
        interval: int,
        request_context: _RequestContext | None = None,
    ) -> None:
        """Start background backfill task with single-flight de-duplication."""
        key = self._backfill_key(
            node_id=node_id,
            interval=interval,
            start=start,
            end=end,
            context=request_context,
        )
        self._cleanup_expired_backfills()
        if key in self._active_backfills:
            return
        # Process-local single-flight
        ttl_seconds = self._backfill_config.single_flight_ttl_ms / 1000.0
        now = time.monotonic()
        expiry = now + ttl_seconds if ttl_seconds > 0 else now
        token = next(self._backfill_generation)
        self._active_backfills[key] = (expiry, token)
        # Coordinator claim (best-effort, works with in-memory stub)
        lease: Lease | None = None
        try:
            if self._coordinator:
                lease = await self._coordinator.claim(
                    key, lease_ms=self._backfill_config.distributed_lease_ttl_ms
                )
                if lease is None:
                    # Claimed elsewhere; skip
                    self._active_backfills.pop(key, None)
                    return
        except Exception:
            # Coordinator unavailable, proceed with local guard only
            lease = None

        async def _run() -> None:
            success = False
            failure_reason: str | None = None
            try:
                if not self.backfiller:
                    failure_reason = "no_backfiller"
                    return
                await self._execute_backfill_range(
                    start,
                    end,
                    node_id=node_id,
                    interval=interval,
                    target_storage=self.storage_source,
                )
                success = True
            except Exception as exc:
                failure_reason = (
                    f"background_backfill_failed ({exc.__class__.__name__}): {exc}"
                )
                logger.exception(
                    "seamless.backfill.background_failed",
                    extra={
                        "node_id": node_id,
                        "interval": interval,
                        "start": start,
                        "end": end,
                    },
                )
            finally:
                if lease and self._coordinator:
                    try:
                        if success:
                            await self._coordinator.complete(lease)
                        else:
                            await self._coordinator.fail(
                                lease, failure_reason or "background_backfill_failed"
                            )
                    except Exception:
                        pass
                current = self._active_backfills.get(key)
                if current is not None and current[1] == token:
                    self._active_backfills.pop(key, None)

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No running loop; backfill synchronously
            await _run()
        else:
            loop.create_task(_run())
    
    def _merge_ranges(self, ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
        return _RangeOperations.merge(ranges)
    
    def _find_missing_ranges(
        self, start: int, end: int, available_ranges: list[tuple[int, int]], interval: int
    ) -> list[tuple[int, int]]:
        """Find missing ranges using canonical interval-aware coverage math."""
        try:
            window = WarmupWindow(start=start, end=end, interval=interval)
            gaps = _compute_missing_ranges(available_ranges, window)
            return [(g.start, g.end) for g in gaps]
        except Exception:
            # Fallback to naive computation
            if not available_ranges:
                return [(start, end)]
            missing: list[tuple[int, int]] = []
            current = start
            for avail_start, avail_end in sorted(available_ranges):
                if avail_start > current:
                    missing.append((current, min(avail_start, end)))
                current = max(current, avail_end)
                if current >= end:
                    break
            if current < end:
                missing.append((current, end))
            return missing
    
    def _intersect_ranges(
        self, ranges1: list[tuple[int, int]], ranges2: list[tuple[int, int]]
    ) -> list[tuple[int, int]]:
        return _RangeOperations.intersect(ranges1, ranges2)
    
    def _subtract_ranges(
        self,
        from_ranges: list[tuple[int, int]],
        subtract_ranges: list[tuple[int, int]],
        interval: int,
    ) -> list[tuple[int, int]]:
        return _RangeOperations.subtract(from_ranges, subtract_ranges, interval)


class _RangeOperations:
    """Range math helpers used by seamless orchestration."""

    @staticmethod
    def merge(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
        if not ranges:
            return []
        sorted_ranges = sorted(ranges)
        merged = [sorted_ranges[0]]
        for current_start, current_end in sorted_ranges[1:]:
            last_start, last_end = merged[-1]
            if current_start <= last_end:
                merged[-1] = (last_start, max(last_end, current_end))
            else:
                merged.append((current_start, current_end))
        return merged

    @staticmethod
    def intersect(
        ranges1: list[tuple[int, int]],
        ranges2: list[tuple[int, int]],
    ) -> list[tuple[int, int]]:
        result: list[tuple[int, int]] = []
        for start1, end1 in ranges1:
            for start2, end2 in ranges2:
                intersect_start = max(start1, start2)
                intersect_end = min(end1, end2)
                if intersect_start < intersect_end:
                    result.append((intersect_start, intersect_end))
        return _RangeOperations.merge(result)

    @staticmethod
    def subtract(
        from_ranges: list[tuple[int, int]],
        subtract_ranges: list[tuple[int, int]],
        interval: int,
    ) -> list[tuple[int, int]]:
        if not subtract_ranges:
            return list(from_ranges)
        if interval <= 0:
            return _RangeOperations._subtract_without_interval(from_ranges, subtract_ranges)
        return _RangeOperations._subtract_with_interval(from_ranges, subtract_ranges, interval)

    @staticmethod
    def _subtract_without_interval(
        from_ranges: list[tuple[int, int]],
        subtract_ranges: list[tuple[int, int]],
    ) -> list[tuple[int, int]]:
        result = list(from_ranges)
        for sub_start, sub_end in subtract_ranges:
            new_result: list[tuple[int, int]] = []
            for start, end in result:
                if sub_end <= start or sub_start >= end:
                    new_result.append((start, end))
                    continue
                if start < sub_start:
                    new_result.append((start, sub_start))
                if end > sub_end:
                    new_result.append((sub_end, end))
            result = new_result
        return result

    @staticmethod
    def _subtract_with_interval(
        from_ranges: list[tuple[int, int]],
        subtract_ranges: list[tuple[int, int]],
        interval: int,
    ) -> list[tuple[int, int]]:
        remaining: list[tuple[int, int]] = []
        for range_start, range_end in from_ranges:
            segments: list[tuple[int, int]] = [(int(range_start), int(range_end))]
            for sub_start_raw, sub_end_raw in subtract_ranges:
                sub_start = int(sub_start_raw)
                sub_end = int(sub_end_raw)
                if sub_start > sub_end:
                    continue
                segments = _RangeOperations._subtract_segment(segments, sub_start, sub_end, interval)
                if not segments:
                    break
            remaining.extend(segments)
        return _RangeOperations.merge(sorted(remaining))

    @staticmethod
    def _subtract_segment(
        segments: list[tuple[int, int]],
        sub_start: int,
        sub_end: int,
        interval: int,
    ) -> list[tuple[int, int]]:
        new_segments: list[tuple[int, int]] = []
        for seg_start, seg_end in segments:
            if not _RangeOperations._segments_overlap(seg_start, seg_end, sub_start, sub_end):
                new_segments.append((seg_start, seg_end))
                continue
            if not _RangeOperations._is_aligned(seg_start, sub_start, interval):
                new_segments.append((seg_start, seg_end))
                continue

            first = _RangeOperations._aligned_first(seg_start, seg_end, sub_start, interval, sub_end)
            last = _RangeOperations._aligned_last(seg_start, seg_end, sub_end, interval)
            if first is None or last is None or last < first:
                new_segments.append((seg_start, seg_end))
                continue

            if first > seg_start:
                new_segments.append((seg_start, first - interval))
            if last < seg_end:
                new_segments.append((last + interval, seg_end))
        return new_segments

    @staticmethod
    def _segments_overlap(seg_start: int, seg_end: int, sub_start: int, sub_end: int) -> bool:
        return not (sub_end < seg_start or sub_start > seg_end)

    @staticmethod
    def _is_aligned(seg_start: int, sub_start: int, interval: int) -> bool:
        return (seg_start - sub_start) % interval == 0

    @staticmethod
    def _aligned_first(
        seg_start: int, seg_end: int, sub_start: int, interval: int, sub_end: int
    ) -> int | None:
        first = max(seg_start, sub_start)
        remainder = (first - seg_start) % interval
        if remainder:
            first += interval - remainder
        if first > seg_end or first > sub_end:
            return None
        return first

    @staticmethod
    def _aligned_last(
        seg_start: int, seg_end: int, sub_end: int, interval: int
    ) -> int | None:
        last = min(seg_end, sub_end)
        remainder = (last - seg_start) % interval
        last -= remainder
        if last < seg_start:
            return None
        return last


class _DomainGateEvaluator:
    def __init__(
        self,
        *,
        merge_decisions: Callable[[
            _DowngradeDecision | None,
            _DowngradeDecision | None,
        ], _DowngradeDecision | None],
        compute_coverage_ratio: Callable[[SeamlessFetchMetadata], float | None],
        compute_staleness_ms: Callable[[SeamlessFetchMetadata], float | None],
        compare_as_of: Callable[[str, str], int],
        live_state: MutableMapping[tuple[str, str], str],
        logger: logging.Logger,
    ) -> None:
        self._merge_decisions = merge_decisions
        self._compute_coverage_ratio = compute_coverage_ratio
        self._compute_staleness_ms = compute_staleness_ms
        self._compare_as_of = compare_as_of
        self._live_state = live_state
        self._logger = logger

    def evaluate(
        self,
        context: _RequestContext,
        metadata: SeamlessFetchMetadata,
        *,
        node_id: str,
        interval: int,
    ) -> _DowngradeDecision | None:
        domain = context.execution_domain
        if domain in {"backtest", "dryrun"}:
            self._enforce_offline_requirements(context, metadata, node_id, interval)
            return None
        if domain in {"live", "shadow"}:
            return self._evaluate_live_domain(context, metadata, node_id, interval, domain)
        return None

    def _enforce_offline_requirements(
        self,
        context: _RequestContext,
        metadata: SeamlessFetchMetadata,
        node_id: str,
        interval: int,
    ) -> None:
        if context.requested_as_of is None:
            self._logger.error(
                "seamless.domain_gate.missing_as_of",
                extra={
                    "node_id": node_id,
                    "interval": interval,
                    "execution_domain": context.execution_domain,
                    "world_id": context.world_id,
                },
            )
            raise SeamlessDomainPolicyError("as_of is required for backtest/dryrun domains")
        if metadata.artifact is None and metadata.manifest_uri is None:
            self._logger.error(
                "seamless.domain_gate.missing_artifact",
                extra={
                    "node_id": node_id,
                    "interval": interval,
                    "execution_domain": context.execution_domain,
                    "world_id": context.world_id,
                },
            )
            raise SeamlessDomainPolicyError(
                "artifact-backed data is required for backtest/dryrun domains"
            )

    def _evaluate_live_domain(
        self,
        context: _RequestContext,
        metadata: SeamlessFetchMetadata,
        node_id: str,
        interval: int,
        domain: str,
    ) -> _DowngradeDecision | None:
        coverage_ratio = metadata.coverage_ratio
        if coverage_ratio is None:
            coverage_ratio = self._compute_coverage_ratio(metadata)
            metadata.coverage_ratio = coverage_ratio
        staleness_ms = metadata.staleness_ms
        if staleness_ms is None:
            staleness_ms = self._compute_staleness_ms(metadata)
            metadata.staleness_ms = staleness_ms

        decision: _DowngradeDecision | None = None
        decision = self._check_as_of_progress(
            decision,
            context,
            node_id,
            coverage_ratio,
            staleness_ms,
        )

        if (
            context.min_coverage is not None
            and coverage_ratio is not None
            and coverage_ratio < context.min_coverage
        ):
            decision = self._merge_decisions(
                decision,
                _DowngradeDecision(
                    mode=SLAViolationMode.HOLD,
                    reason="coverage_breach",
                    violation=None,
                    coverage_ratio=coverage_ratio,
                    staleness_ms=staleness_ms,
                ),
            )

        if (
            context.max_lag_seconds is not None
            and staleness_ms is not None
            and staleness_ms > context.max_lag_seconds * 1000
        ):
            decision = self._merge_decisions(
                decision,
                _DowngradeDecision(
                    mode=SLAViolationMode.HOLD,
                    reason="freshness_breach",
                    violation=None,
                    coverage_ratio=coverage_ratio,
                    staleness_ms=staleness_ms,
                ),
            )

        if decision is not None:
            self._log_downgrade(context, metadata, node_id, interval, domain, decision)
        return decision

    def _check_as_of_progress(
        self,
        base: _DowngradeDecision | None,
        context: _RequestContext,
        node_id: str,
        coverage_ratio: float | None,
        staleness_ms: float | None,
    ) -> _DowngradeDecision | None:
        requested_as_of = context.requested_as_of
        if not requested_as_of:
            return base
        key = (context.world_id, node_id)
        previous = self._live_state.get(key)
        world_label = context.world_id or ""
        if previous is not None:
            comparison = self._compare_as_of(requested_as_of, previous)
            if comparison < 0:
                return self._merge_decisions(
                    base,
                    _DowngradeDecision(
                        mode=SLAViolationMode.HOLD,
                        reason="as_of_regression",
                        violation=None,
                        coverage_ratio=coverage_ratio,
                        staleness_ms=staleness_ms,
                    ),
                )
            self._live_state[key] = requested_as_of
            if comparison > 0:
                sdk_metrics.observe_as_of_advancement_event(
                    node_id=node_id,
                    world_id=world_label,
                )
            return base
        self._live_state[key] = requested_as_of
        sdk_metrics.observe_as_of_advancement_event(
            node_id=node_id,
            world_id=world_label,
        )
        return base

    def _log_downgrade(
        self,
        context: _RequestContext,
        metadata: SeamlessFetchMetadata,
        node_id: str,
        interval: int,
        domain: str,
        decision: _DowngradeDecision,
    ) -> None:
        fingerprint = metadata.dataset_fingerprint
        if fingerprint is None and metadata.artifact is not None:
            fingerprint = getattr(metadata.artifact, "dataset_fingerprint", None)
        as_of_value: Any | None = metadata.as_of
        if as_of_value is None:
            as_of_value = metadata.requested_as_of or context.requested_as_of
        self._logger.warning(
            "seamless.domain_gate.downgrade",
            extra={
                "node_id": node_id,
                "interval": interval,
                "world_id": context.world_id,
                "execution_domain": domain,
                "reason": decision.reason,
                "dataset_fingerprint": fingerprint,
                "as_of": as_of_value,
            },
        )


class _AvailabilityPipeline:
    def __init__(
        self,
        *,
        provider: "SeamlessDataProvider",
        tracker: "_SLATracker | None",
        request_context: _RequestContext | None,
    ) -> None:
        self._provider = provider
        self._tracker = tracker
        self._context = request_context

    async def ensure(
        self,
        start: int,
        end: int,
        *,
        node_id: str,
        interval: int,
    ) -> bool:
        available_ranges = await self._observe_coverage(node_id, interval)
        missing_ranges = self._provider._find_missing_ranges(
            start, end, available_ranges, interval
        )
        if not self._respect_sync_gap(missing_ranges, interval, node_id):
            return False
        if not missing_ranges:
            return True
        await self._backfill_missing(missing_ranges, node_id, interval)
        updated_ranges = await self._observe_coverage(node_id, interval)
        final_missing = self._provider._find_missing_ranges(
            start, end, updated_ranges, interval
        )
        return len(final_missing) == 0

    async def _observe_coverage(
        self, node_id: str, interval: int
    ) -> list[tuple[int, int]]:
        coverage_coro = self._provider.coverage(node_id=node_id, interval=interval)
        if self._tracker:
            return await self._tracker.observe_async(
                "storage_wait",
                self._tracker.policy.max_wait_storage_ms,
                coverage_coro,
            )
        return await coverage_coro

    def _respect_sync_gap(
        self,
        missing_ranges: list[tuple[int, int]],
        interval: int,
        node_id: str,
    ) -> bool:
        sla = self._provider._sla
        if not sla or sla.max_sync_gap_bars is None or not missing_ranges:
            return True
        missing_bars = 0
        for gap_start, gap_end in missing_ranges:
            if interval <= 0:
                continue
            missing_bars += max(0, int((gap_end - gap_start) / interval))
        if missing_bars <= sla.max_sync_gap_bars:
            return True
        interval_ms = max(interval, 0) * 1000
        elapsed_ms = missing_bars * interval_ms
        budget_ms = sla.max_sync_gap_bars * interval_ms
        if self._tracker:
            self._tracker.handle_violation(
                "sync_gap",
                elapsed_ms=float(elapsed_ms),
                budget_ms=int(budget_ms) if interval_ms else None,
            )
            return False
        raise SeamlessSLAExceeded(
            "sync_gap",
            node_id=node_id,
            elapsed_ms=float(elapsed_ms),
            budget_ms=int(budget_ms) if interval_ms else None,
        )

    async def _backfill_missing(
        self,
        missing_ranges: list[tuple[int, int]],
        node_id: str,
        interval: int,
    ) -> None:
        provider = self._provider
        backfiller = provider.backfiller
        if backfiller is None or provider.strategy == DataAvailabilityStrategy.FAIL_FAST:
            return
        for missing_start, missing_end in missing_ranges:
            can_backfill = await backfiller.can_backfill(
                missing_start, missing_end, node_id=node_id, interval=interval
            )
            if not can_backfill:
                continue
            if provider.enable_background_backfill:
                await provider._start_background_backfill(
                    missing_start,
                    missing_end,
                    node_id=node_id,
                    interval=interval,
                    request_context=self._context,
                )
                continue
            lease, skip = await self._claim_lease(missing_start, missing_end, node_id, interval)
            if skip:
                continue
            try:
                await provider._execute_backfill_range(
                    missing_start,
                    missing_end,
                    node_id=node_id,
                    interval=interval,
                    target_storage=provider.storage_source,
                    sla_tracker=self._tracker,
                )
                await self._complete_lease(lease)
            except Exception as exc:
                await self._fail_lease(lease, f"synchronous_backfill_failed: {exc}")
                raise

    async def _claim_lease(
        self,
        start: int,
        end: int,
        node_id: str,
        interval: int,
    ) -> tuple[Lease | None, bool]:
        coordinator = self._provider._coordinator
        if coordinator is None:
            return None, False
        try:
            lease_key = self._provider._backfill_key(
                node_id=node_id,
                interval=interval,
                start=start,
                end=end,
                context=self._context,
            )
            lease = await coordinator.claim(
                lease_key,
                lease_ms=self._provider._backfill_config.distributed_lease_ttl_ms,
            )
        except Exception:
            return None, False
        if lease is None:
            return None, True
        return lease, False

    async def _complete_lease(self, lease: Lease | None) -> None:
        coordinator = self._provider._coordinator
        if lease is None or coordinator is None:
            return
        try:
            await coordinator.complete(lease)
        except Exception:
            pass

    async def _fail_lease(self, lease: Lease | None, reason: str) -> None:
        coordinator = self._provider._coordinator
        if lease is None or coordinator is None:
            return
        try:
            await coordinator.fail(lease, reason)
        except Exception:
            pass


class _SeamlessFetchPlanner:
    def __init__(
        self,
        *,
        provider: "SeamlessDataProvider",
        node_id: str,
        interval: int,
        tracker: "_SLATracker | None",
        request_context: _RequestContext | None,
    ) -> None:
        self._provider = provider
        self._node_id = node_id
        self._interval = int(interval)
        self._tracker = tracker
        self._context = request_context

    async def fetch(self, start: int, end: int) -> pd.DataFrame:
        result_frames: list[pd.DataFrame] = []
        remaining_ranges: list[tuple[int, int]] = [(start, end)]
        for source in self._provider._get_ordered_sources():
            if not remaining_ranges:
                break
            remaining_ranges = await self._consume_source(
                source, remaining_ranges, result_frames
            )
        if remaining_ranges and self._provider.backfiller:
            backfilled = await self._backfill_remaining(remaining_ranges)
            result_frames.extend(backfilled)
        if result_frames:
            combined = pd.concat(result_frames, ignore_index=True)
            if "ts" in combined.columns:
                combined = combined.sort_values("ts").reset_index(drop=True)
            return combined
        return pd.DataFrame()

    async def _consume_source(
        self,
        source: DataSource,
        ranges: list[tuple[int, int]],
        result_frames: list[pd.DataFrame],
    ) -> list[tuple[int, int]]:
        new_remaining: list[tuple[int, int]] = []
        for range_start, range_end in ranges:
            try:
                coverage = await self._observe_source_coverage(source, range_start, range_end)
            except Exception as exc:
                if isinstance(exc, SeamlessSLAExceeded):
                    raise
                new_remaining.append((range_start, range_end))
                continue
            available = _RangeOperations.intersect([(range_start, range_end)], coverage)
            if available:
                frames = await self._fetch_available(source, available)
                result_frames.extend(frames)
                still_missing = _RangeOperations.subtract(
                    [(range_start, range_end)], available, self._interval
                )
                new_remaining.extend(still_missing)
            else:
                new_remaining.append((range_start, range_end))
        return new_remaining

    async def _observe_source_coverage(
        self,
        source: DataSource,
        range_start: int,
        range_end: int,
    ) -> list[tuple[int, int]]:
        coverage_coro = source.coverage(node_id=self._node_id, interval=self._interval)
        if self._tracker and source.priority == DataSourcePriority.STORAGE:
            return await self._tracker.observe_async(
                "storage_wait",
                self._tracker.policy.max_wait_storage_ms,
                coverage_coro,
            )
        return await coverage_coro

    async def _fetch_available(
        self,
        source: DataSource,
        available_ranges: list[tuple[int, int]],
    ) -> list[pd.DataFrame]:
        frames: list[pd.DataFrame] = []
        for avail_start, avail_end in available_ranges:
            fetch_coro = source.fetch(
                avail_start,
                avail_end,
                node_id=self._node_id,
                interval=self._interval,
            )
            if self._tracker and source.priority == DataSourcePriority.STORAGE:
                frame = await self._tracker.observe_async(
                    "storage_wait",
                    self._tracker.policy.max_wait_storage_ms,
                    fetch_coro,
                )
            else:
                frame = await fetch_coro
            if not frame.empty:
                frames.append(frame)
        return frames

    async def _backfill_remaining(
        self, remaining_ranges: list[tuple[int, int]]
    ) -> list[pd.DataFrame]:
        result: list[pd.DataFrame] = []
        for range_start, range_end in remaining_ranges:
            try:
                frames = await self._provider._execute_backfill_range(
                    range_start,
                    range_end,
                    node_id=self._node_id,
                    interval=self._interval,
                    target_storage=self._provider.storage_source,
                    sla_tracker=self._tracker,
                    collect_results=True,
                )
            except Exception as exc:
                if isinstance(exc, SeamlessSLAExceeded):
                    raise
                continue
            non_empty = [frame for frame in frames if not frame.empty]
            if non_empty:
                result.append(pd.concat(non_empty, ignore_index=True))
        return result


class _SLATracker:
    def __init__(self, policy: SLAPolicy, *, node_id: str, interval: int) -> None:
        self.policy = policy
        self.node_id = node_id
        self.interval = int(interval)
        self._request_start = time.monotonic()
        self._violation: _SLAViolationDetail | None = None

    async def observe_async(
        self, phase: str, budget_ms: int | None, awaitable: Awaitable[T]
    ) -> T:
        start = time.monotonic()
        try:
            result = await awaitable
        except Exception:
            elapsed_ms = (time.monotonic() - start) * 1000.0
            self._record_phase(phase, elapsed_ms, budget_ms)
            raise
        else:
            elapsed_ms = (time.monotonic() - start) * 1000.0
            self._record_phase(phase, elapsed_ms, budget_ms)
            return result

    def observe_total(self) -> None:
        elapsed_ms = (time.monotonic() - self._request_start) * 1000.0
        self._record_phase("total", elapsed_ms, self.policy.total_deadline_ms)

    @property
    def violation(self) -> _SLAViolationDetail | None:
        return self._violation

    def handle_violation(
        self, phase: str, *, elapsed_ms: float, budget_ms: int | None
    ) -> None:
        detail = _SLAViolationDetail(phase=phase, elapsed_ms=elapsed_ms, budget_ms=budget_ms)
        if self._violation is None:
            self._violation = detail
        logger.warning(
            "seamless.sla.phase_exceeded",
            extra={
                "node_id": self.node_id,
                "phase": phase,
                "elapsed_ms": elapsed_ms,
                "budget_ms": budget_ms,
                "mode": self.policy.on_violation.value,
            },
        )
        if self.policy.on_violation is SLAViolationMode.FAIL_FAST:
            raise SeamlessSLAExceeded(
                phase,
                node_id=self.node_id,
                elapsed_ms=elapsed_ms,
                budget_ms=budget_ms,
            )

    def _record_phase(self, phase: str, elapsed_ms: float, budget_ms: int | None) -> None:
        sdk_metrics.observe_sla_phase_duration(
            node_id=self.node_id,
            interval=self.interval,
            phase=phase,
            duration_ms=elapsed_ms,
        )
        if budget_ms is not None and elapsed_ms > budget_ms:
            self.handle_violation(phase, elapsed_ms=elapsed_ms, budget_ms=budget_ms)


__all__ = [
    "DataAvailabilityStrategy",
    "DataSourcePriority",
    "DataSource",
    "AutoBackfiller",
    "LiveDataFeed",
    "ConformancePipelineError",
    "BackfillConfig",
    "SeamlessDataProvider",
    "SeamlessFetchResult",
    "SeamlessFetchMetadata",
]
