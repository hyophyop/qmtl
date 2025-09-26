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
)
from abc import ABC
from dataclasses import dataclass
import pandas as pd
from enum import Enum
import asyncio
import logging
import math
import os
import time
import hashlib
import json

from .history_coverage import (
    merge_coverage as _merge_coverage,
    compute_missing_ranges as _compute_missing_ranges,
    WarmupWindow,
)
from . import metrics as sdk_metrics
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

logger = logging.getLogger(__name__)

"""Seamless Data Provider interfaces for transparent data access with auto-backfill."""

T = TypeVar("T")


CONFORMANCE_VERSION = "v1"


@dataclass(slots=True)
class SeamlessFetchMetadata:
    node_id: str
    interval: int
    requested_range: tuple[int, int]
    rows: int
    coverage_bounds: tuple[int, int] | None
    conformance_flags: dict[str, int]
    conformance_warnings: tuple[str, ...]
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


class SeamlessDataProvider(ABC):
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
        partial_ok: bool = False,
        registrar: ArtifactRegistrar | None = None,
        stabilization_bars: int = 2,
    ) -> None:
        self.strategy = strategy
        self.cache_source = cache_source
        self.storage_source = storage_source
        self.backfiller = backfiller
        self.live_feed = live_feed
        self.max_backfill_chunk_size = max_backfill_chunk_size
        self.enable_background_backfill = enable_background_backfill
        self._conformance = conformance
        self._coordinator = coordinator or self._create_default_coordinator()
        self._sla = sla
        self._partial_ok = bool(partial_ok)
        self._last_conformance_report: Optional[ConformanceReport] = None
        self._registrar = registrar
        self._stabilization_bars = max(0, int(stabilization_bars))
        # Preserve last fetch metadata for introspection
        self._last_fetch_metadata: Optional[SeamlessFetchMetadata] = None

        # Internal state
        self._active_backfills: dict[str, bool] = {}

    @property
    def last_conformance_report(self) -> Optional[ConformanceReport]:
        """Return the most recent conformance report emitted by ``fetch``."""

        return self._last_conformance_report

    @property
    def last_fetch_metadata(self) -> Optional[SeamlessFetchMetadata]:
        """Return metadata describing the last call to :meth:`fetch`."""

        return self._last_fetch_metadata

    def _create_default_coordinator(self) -> BackfillCoordinator:
        url = os.getenv("QMTL_SEAMLESS_COORDINATOR_URL", "").strip()
        if url:
            try:
                return DistributedBackfillCoordinator(url)
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("seamless.coordinator.init_failed", exc_info=exc)
        return InMemoryBackfillCoordinator()

    def _build_sla_tracker(self, node_id: str) -> "_SLATracker | None":
        if not self._sla:
            return None
        return _SLATracker(self._sla, node_id=node_id)

    async def fetch(
        self, start: int, end: int, *, node_id: str, interval: int
    ) -> pd.DataFrame:
        """
        Fetch data transparently from available sources.
        
        Implementation follows the priority order and strategy configuration.
        """
        self._last_conformance_report = None
        self._last_fetch_metadata = None
        tracker = self._build_sla_tracker(node_id)

        if self.strategy == DataAvailabilityStrategy.FAIL_FAST:
            result = await self._fetch_fail_fast(
                start, end, node_id=node_id, interval=interval, sla_tracker=tracker
            )
        elif self.strategy == DataAvailabilityStrategy.AUTO_BACKFILL:
            result = await self._fetch_auto_backfill(
                start, end, node_id=node_id, interval=interval, sla_tracker=tracker
            )
        elif self.strategy == DataAvailabilityStrategy.PARTIAL_FILL:
            result = await self._fetch_partial_fill(
                start, end, node_id=node_id, interval=interval, sla_tracker=tracker
            )
        else:  # SEAMLESS
            result = await self._fetch_seamless(
                start, end, node_id=node_id, interval=interval, sla_tracker=tracker
            )

        response = self._finalize_response(
            result,
            start=start,
            end=end,
            node_id=node_id,
            interval=interval,
        )

        downgrade: _DowngradeDecision | None = None
        if tracker:
            tracker.observe_total()
            downgrade = self._resolve_downgrade(tracker, response.metadata)

        if downgrade:
            self._apply_downgrade(
                response,
                downgrade,
                node_id=node_id,
                interval=interval,
            )

        return response
    
    async def coverage(
        self, *, node_id: str, interval: int
    ) -> list[tuple[int, int]]:
        """Return combined coverage from all sources."""
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
    
    async def ensure_data_available(
        self,
        start: int,
        end: int,
        *,
        node_id: str,
        interval: int,
        sla_tracker: "_SLATracker | None" = None,
    ) -> bool:
        """
        Ensure data is available for the given range.
        
        If data is missing and auto-backfill is enabled, trigger backfill.
        Returns True if data will be available after this call.
        """
        tracker = sla_tracker or self._build_sla_tracker(node_id)

        # Check current availability
        if tracker:
            available_ranges = await tracker.observe_async(
                "storage_wait",
                tracker.policy.max_wait_storage_ms,
                self.coverage(node_id=node_id, interval=interval),
            )
        else:
            available_ranges = await self.coverage(node_id=node_id, interval=interval)
        missing_ranges = self._find_missing_ranges(start, end, available_ranges, interval)

        if self._sla and self._sla.max_sync_gap_bars is not None and missing_ranges:
            missing_bars = 0
            for gap_start, gap_end in missing_ranges:
                if interval <= 0:
                    continue
                missing_bars += max(0, int((gap_end - gap_start) / interval))
            if missing_bars > self._sla.max_sync_gap_bars:
                interval_ms = max(interval, 0) * 1000
                elapsed_ms = missing_bars * interval_ms
                budget_ms = self._sla.max_sync_gap_bars * interval_ms
                if tracker:
                    tracker.handle_violation(
                        "sync_gap",
                        elapsed_ms=float(elapsed_ms),
                        budget_ms=int(budget_ms) if interval_ms else None,
                    )
                else:
                    raise SeamlessSLAExceeded(
                        "sync_gap",
                        node_id=node_id,
                        elapsed_ms=float(elapsed_ms),
                        budget_ms=int(budget_ms) if interval_ms else None,
                    )
                return False

        if not missing_ranges:
            return True
        
        # Try to backfill missing ranges
        if self.backfiller and self.strategy != DataAvailabilityStrategy.FAIL_FAST:
            for missing_start, missing_end in missing_ranges:
                can_backfill = await self.backfiller.can_backfill(
                    missing_start, missing_end, node_id=node_id, interval=interval
                )
                if can_backfill:
                    if self.enable_background_backfill:
                        await self._start_background_backfill(
                            missing_start,
                            missing_end,
                            node_id=node_id,
                            interval=interval,
                        )
                    else:
                        lease: Lease | None = None
                        skip_due_to_conflict = False
                        if self._coordinator:
                            try:
                                lease = await self._coordinator.claim(
                                    f"{node_id}:{interval}:{missing_start}:{missing_end}",
                                    lease_ms=60_000,
                                )
                            except Exception:
                                lease = None
                            else:
                                if lease is None:
                                    skip_due_to_conflict = True
                        if skip_due_to_conflict:
                            continue

                        try:
                            sdk_metrics.observe_backfill_start(node_id, interval)
                            backfill_coro = self.backfiller.backfill(
                                missing_start,
                                missing_end,
                                node_id=node_id,
                                interval=interval,
                                target_storage=self.storage_source,
                            )
                            if sla_tracker:
                                await sla_tracker.observe_async(
                                    "backfill_wait",
                                    sla_tracker.policy.max_wait_backfill_ms,
                                    backfill_coro,
                                )
                            else:
                                await backfill_coro
                            sdk_metrics.observe_backfill_complete(
                                node_id, interval, missing_end
                            )
                            if lease and self._coordinator:
                                try:
                                    await self._coordinator.complete(lease)
                                except Exception:
                                    pass
                        except Exception as exc:
                            sdk_metrics.observe_backfill_failure(node_id, interval)
                            if lease and self._coordinator:
                                try:
                                    await self._coordinator.fail(
                                        lease,
                                        f"synchronous_backfill_failed: {exc}",
                                    )
                                except Exception:
                                    pass
                            raise
        
        # Re-check availability
        if tracker:
            updated_ranges = await tracker.observe_async(
                "storage_wait",
                tracker.policy.max_wait_storage_ms,
                self.coverage(node_id=node_id, interval=interval),
            )
        else:
            updated_ranges = await self.coverage(node_id=node_id, interval=interval)
        final_missing = self._find_missing_ranges(start, end, updated_ranges, interval)

        return len(final_missing) == 0
    
    def _get_ordered_sources(self) -> list[DataSource]:
        """Get data sources in priority order."""
        sources = []
        if self.cache_source:
            sources.append(self.cache_source)
        if self.storage_source:
            sources.append(self.storage_source)
        return sorted(sources, key=lambda s: s.priority.value)
    
    async def _fetch_seamless(
        self,
        start: int,
        end: int,
        *,
        node_id: str,
        interval: int,
        sla_tracker: "_SLATracker | None" = None,
    ) -> pd.DataFrame:
        """Implement seamless fetching strategy."""
        # Try each source in priority order
        result_frames = []
        remaining_ranges = [(start, end)]

        # Reset report tracking for this request
        self._last_conformance_report = None
        
        for source in self._get_ordered_sources():
            if not remaining_ranges:
                break
                
            new_remaining = []
            for range_start, range_end in remaining_ranges:
                try:
                    # Check what this source can provide
                    coverage_coro = source.coverage(node_id=node_id, interval=interval)
                    if sla_tracker and source.priority == DataSourcePriority.STORAGE:
                        source_coverage = await sla_tracker.observe_async(
                            "storage_wait",
                            sla_tracker.policy.max_wait_storage_ms,
                            coverage_coro,
                        )
                    else:
                        source_coverage = await coverage_coro
                    available_in_range = self._intersect_ranges(
                        [(range_start, range_end)], source_coverage
                    )
                    
                    if available_in_range:
                        # Fetch available data from this source
                        for avail_start, avail_end in available_in_range:
                            fetch_coro = source.fetch(
                                avail_start, avail_end, node_id=node_id, interval=interval
                            )
                            if sla_tracker and source.priority == DataSourcePriority.STORAGE:
                                frame = await sla_tracker.observe_async(
                                    "storage_wait",
                                    sla_tracker.policy.max_wait_storage_ms,
                                    fetch_coro,
                                )
                            else:
                                frame = await fetch_coro
                            if not frame.empty:
                                result_frames.append(frame)
                        
                        # Update remaining ranges
                        still_missing = self._subtract_ranges(
                            [(range_start, range_end)],
                            available_in_range,
                            interval,
                        )
                        new_remaining.extend(still_missing)
                    else:
                        new_remaining.append((range_start, range_end))
                except Exception as exc:
                    if isinstance(exc, SeamlessSLAExceeded):
                        raise
                    # If source fails, keep the range for other sources
                    new_remaining.append((range_start, range_end))
            
            remaining_ranges = new_remaining
        
        # Try auto-backfill for remaining ranges
        if remaining_ranges and self.backfiller:
            for range_start, range_end in remaining_ranges:
                try:
                    sdk_metrics.observe_backfill_start(node_id, interval)
                    backfill_coro = self.backfiller.backfill(
                        range_start,
                        range_end,
                        node_id=node_id,
                        interval=interval,
                        target_storage=self.storage_source,
                    )
                    if sla_tracker:
                        backfilled = await sla_tracker.observe_async(
                            "backfill_wait",
                            sla_tracker.policy.max_wait_backfill_ms,
                            backfill_coro,
                        )
                    else:
                        backfilled = await backfill_coro
                    if not backfilled.empty:
                        result_frames.append(backfilled)
                    sdk_metrics.observe_backfill_complete(node_id, interval, range_end)
                except Exception as exc:
                    if isinstance(exc, SeamlessSLAExceeded):
                        raise
                    sdk_metrics.observe_backfill_failure(node_id, interval)
                    continue
        
        # Combine all frames and sort by timestamp
        if result_frames:
            combined = pd.concat(result_frames, ignore_index=True)
            if "ts" in combined.columns:
                combined = combined.sort_values("ts").reset_index(drop=True)
            return combined

        return pd.DataFrame()
    
    async def _fetch_fail_fast(
        self,
        start: int,
        end: int,
        *,
        node_id: str,
        interval: int,
        sla_tracker: "_SLATracker | None" = None,
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
    ) -> pd.DataFrame:
        """Auto-backfill strategy - ensure data is backfilled before returning."""
        await self.ensure_data_available(
            start,
            end,
            node_id=node_id,
            interval=interval,
            sla_tracker=sla_tracker,
        )
        return await self._fetch_seamless(
            start, end, node_id=node_id, interval=interval, sla_tracker=sla_tracker
        )
    
    async def _fetch_partial_fill(
        self,
        start: int,
        end: int,
        *,
        node_id: str,
        interval: int,
        sla_tracker: "_SLATracker | None" = None,
    ) -> pd.DataFrame:
        """Partial fill strategy - return what's available, backfill in background."""
        # Start background backfill but don't wait
        if self.backfiller:
            await self._start_background_backfill(
                start, end, node_id=node_id, interval=interval
            )

        # Return what's currently available
        return await self._fetch_seamless(
            start, end, node_id=node_id, interval=interval, sla_tracker=sla_tracker
        )

    # ------------------------------------------------------------------
    def _finalize_response(
        self,
        frame: pd.DataFrame,
        *,
        start: int,
        end: int,
        node_id: str,
        interval: int,
    ) -> SeamlessFetchResult:
        if not isinstance(frame, pd.DataFrame):
            frame = pd.DataFrame()

        if frame.empty:
            metadata = SeamlessFetchMetadata(
                node_id=node_id,
                interval=int(interval),
                requested_range=(int(start), int(end)),
                rows=0,
                coverage_bounds=None,
                conformance_flags={},
                conformance_warnings=(),
                dataset_fingerprint=None,
                as_of=None,
                manifest_uri=None,
                artifact=None,
            )
            self._last_conformance_report = None
            self._sync_metadata_attrs(frame, metadata)
            return SeamlessFetchResult(frame, metadata)

        normalized = frame
        report: ConformanceReport | None = None
        if self._conformance:
            try:
                normalized, report = self._conformance.normalize(
                    frame,
                    schema=None,
                    interval=interval,
                )
            except ConformancePipelineError:
                raise
            except Exception:  # pragma: no cover - defensive guard
                report = ConformanceReport()
                normalized = frame.copy()
        else:
            normalized = frame.copy()
            report = None

        if report is None:
            report = ConformanceReport()
        self._last_conformance_report = report

        if self._conformance:
            try:
                sdk_metrics.observe_conformance_report(
                    node_id=node_id,
                    flags=report.flags_counts,
                    warnings=report.warnings,
                )
            except Exception:  # pragma: no cover - best effort metrics
                pass

        if (report.warnings or report.flags_counts) and not self._partial_ok:
            raise ConformancePipelineError(report)

        stabilized = self._stabilize_frame(normalized)

        if stabilized.empty:
            metadata = SeamlessFetchMetadata(
                node_id=node_id,
                interval=int(interval),
                requested_range=(int(start), int(end)),
                rows=0,
                coverage_bounds=None,
                conformance_flags=dict(report.flags_counts),
                conformance_warnings=report.warnings,
                dataset_fingerprint=None,
                as_of=None,
                manifest_uri=None,
                artifact=None,
            )
            self._sync_metadata_attrs(stabilized, metadata)
            return SeamlessFetchResult(stabilized, metadata)

        coverage_bounds = self._coverage_bounds(stabilized)
        metadata_payload = {
            "node_id": node_id,
            "interval": int(interval),
            "coverage_bounds": coverage_bounds,
            "requested_bounds": (int(start), int(end)),
            "conformance_version": CONFORMANCE_VERSION,
        }
        fingerprint = self._compute_dataset_fingerprint(stabilized, metadata_payload)
        as_of = int(time.time())
        manifest_uri: str | None = None

        publication: ArtifactPublication | None = None
        if self._registrar and coverage_bounds is not None:
            try:
                publication = self._registrar.publish(
                    stabilized,
                    node_id=node_id,
                    interval=interval,
                    coverage_bounds=coverage_bounds,
                    fingerprint=fingerprint,
                    as_of=as_of,
                    conformance_flags=report.flags_counts,
                    conformance_warnings=report.warnings,
                    request_window=(int(start), int(end)),
                )
            except Exception:  # pragma: no cover - publication failures shouldn't crash
                publication = None

        if publication:
            fingerprint = publication.dataset_fingerprint
            as_of = publication.as_of
            coverage_bounds = publication.coverage_bounds
            manifest_uri = publication.manifest_uri

        metadata = SeamlessFetchMetadata(
            node_id=node_id,
            interval=int(interval),
            requested_range=(int(start), int(end)),
            rows=int(len(stabilized)),
            coverage_bounds=coverage_bounds,
            conformance_flags=dict(report.flags_counts),
            conformance_warnings=report.warnings,
            dataset_fingerprint=fingerprint,
            as_of=as_of,
            manifest_uri=manifest_uri,
            artifact=publication,
        )

        self._sync_metadata_attrs(stabilized, metadata)

        # expose last fetch metadata for callers
        self._last_fetch_metadata = metadata
        return SeamlessFetchResult(stabilized, metadata)

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
                "manifest_uri": metadata.manifest_uri,
                "requested_range": metadata.requested_range,
                "rows": metadata.rows,
                "downgraded": metadata.downgraded,
                "downgrade_mode": metadata.downgrade_mode,
                "downgrade_reason": metadata.downgrade_reason,
                "sla_violation": metadata.sla_violation,
                "coverage_ratio": metadata.coverage_ratio,
                "staleness_ms": metadata.staleness_ms,
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

        coverage_ratio = self._compute_coverage_ratio(metadata)
        staleness_ms = self._compute_staleness_ms(metadata)
        violation = tracker.violation

        mode: SLAViolationMode | None = None
        reason: str | None = None

        if violation:
            mode = self._sla.on_violation
            reason = "sla_violation"

        if (
            self._sla.min_coverage is not None
            and coverage_ratio is not None
            and coverage_ratio < self._sla.min_coverage
        ):
            mode = SLAViolationMode.HOLD
            reason = "coverage_breach"

        if (
            self._sla.max_lag_seconds is not None
            and staleness_ms is not None
            and staleness_ms > self._sla.max_lag_seconds * 1000
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

    def _canonicalize_value(self, value: Any) -> Any:
        if isinstance(value, (int, float, str, bool)):
            return value
        if pd.isna(value):
            return None
        if isinstance(value, (pd.Timestamp, pd.Timedelta)):
            return int(value.value)
        if hasattr(value, "item"):
            try:
                return value.item()
            except Exception:  # pragma: no cover - fallback to string
                pass
        return str(value)

    def _canonicalize_frame(self, frame: pd.DataFrame) -> list[dict[str, Any]]:
        columns = list(frame.columns)
        if "ts" in columns:
            columns = ["ts"] + [col for col in columns if col != "ts"]
        else:
            columns.sort()
        records: list[dict[str, Any]] = []
        for _, row in frame[columns].iterrows():
            record = {col: self._canonicalize_value(row[col]) for col in columns}
            records.append(record)
        return records

    def _normalize_metadata(self, metadata: dict[str, Any]) -> dict[str, Any]:
        normalized: dict[str, Any] = {}
        for key, value in metadata.items():
            if isinstance(value, dict):
                normalized[key] = self._normalize_metadata(value)
            elif isinstance(value, (list, tuple)):
                normalized[key] = [self._canonicalize_value(v) for v in value]
            else:
                normalized[key] = self._canonicalize_value(value)
        return normalized

    def _compute_dataset_fingerprint(
        self, frame: pd.DataFrame, metadata: dict[str, Any]
    ) -> str:
        payload = {
            "frame": self._canonicalize_frame(frame),
            "metadata": self._normalize_metadata(metadata),
        }
        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
        digest = hashlib.sha256(serialized).hexdigest()
        return f"lake:sha256:{digest}"

    async def _start_background_backfill(
        self, start: int, end: int, *, node_id: str, interval: int
    ) -> None:
        """Start background backfill task with single-flight de-duplication."""
        key = f"{node_id}:{interval}:{start}:{end}"
        if self._active_backfills.get(key):
            return
        # Process-local single-flight
        self._active_backfills[key] = True
        # Coordinator claim (best-effort, works with in-memory stub)
        lease: Lease | None = None
        try:
            if self._coordinator:
                lease = await self._coordinator.claim(key, lease_ms=60_000)
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
                sdk_metrics.observe_backfill_start(node_id, interval)
                await self.backfiller.backfill(
                    start,
                    end,
                    node_id=node_id,
                    interval=interval,
                    target_storage=self.storage_source,
                )
                sdk_metrics.observe_backfill_complete(node_id, interval, end)
                success = True
            except Exception as exc:
                failure_reason = (
                    f"background_backfill_failed ({exc.__class__.__name__}): {exc}"
                )
                sdk_metrics.observe_backfill_failure(node_id, interval)
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
                self._active_backfills.pop(key, None)

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No running loop; backfill synchronously
            await _run()
        else:
            loop.create_task(_run())
    
    def _merge_ranges(self, ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
        """Merge overlapping ranges."""
        if not ranges:
            return []
        
        sorted_ranges = sorted(ranges)
        merged = [sorted_ranges[0]]
        
        for current_start, current_end in sorted_ranges[1:]:
            last_start, last_end = merged[-1]
            
            if current_start <= last_end:
                # Overlapping ranges, merge them
                merged[-1] = (last_start, max(last_end, current_end))
            else:
                # Non-overlapping, add as new range
                merged.append((current_start, current_end))
        
        return merged
    
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
        """Find intersection of two range lists."""
        result = []
        
        for start1, end1 in ranges1:
            for start2, end2 in ranges2:
                intersect_start = max(start1, start2)
                intersect_end = min(end1, end2)
                
                if intersect_start < intersect_end:
                    result.append((intersect_start, intersect_end))
        
        return self._merge_ranges(result)
    
    def _subtract_ranges(
        self,
        from_ranges: list[tuple[int, int]],
        subtract_ranges: list[tuple[int, int]],
        interval: int,
    ) -> list[tuple[int, int]]:
        """Subtract ranges from other ranges using interval-aware semantics."""
        if not subtract_ranges:
            return list(from_ranges)

        if interval <= 0:
            # Fallback to naive subtraction when interval metadata is unavailable
            result = list(from_ranges)
            for sub_start, sub_end in subtract_ranges:
                new_result = []
                for start, end in result:
                    if sub_end <= start or sub_start >= end:
                        new_result.append((start, end))
                    else:
                        if start < sub_start:
                            new_result.append((start, sub_start))
                        if end > sub_end:
                            new_result.append((sub_end, end))
                result = new_result
            return result

        remaining: list[tuple[int, int]] = []

        for range_start, range_end in from_ranges:
            segments: list[tuple[int, int]] = [(int(range_start), int(range_end))]

            for sub_start_raw, sub_end_raw in subtract_ranges:
                sub_start = int(sub_start_raw)
                sub_end = int(sub_end_raw)
                if sub_start > sub_end:
                    continue

                new_segments: list[tuple[int, int]] = []
                for seg_start, seg_end in segments:
                    if sub_end < seg_start or sub_start > seg_end:
                        new_segments.append((seg_start, seg_end))
                        continue

                    # Only subtract bars that land on the same interval grid
                    if (seg_start - sub_start) % interval != 0:
                        new_segments.append((seg_start, seg_end))
                        continue

                    first = max(seg_start, sub_start)
                    remainder = (first - seg_start) % interval
                    if remainder:
                        first += interval - remainder

                    if first > seg_end or first > sub_end:
                        new_segments.append((seg_start, seg_end))
                        continue

                    last = min(seg_end, sub_end)
                    remainder = (last - seg_start) % interval
                    last -= remainder

                    if last < first:
                        new_segments.append((seg_start, seg_end))
                        continue

                    if first > seg_start:
                        new_segments.append((seg_start, first - interval))
                    if last < seg_end:
                        new_segments.append((last + interval, seg_end))

                segments = new_segments

            remaining.extend(segments)

        return self._merge_ranges(sorted(remaining))


class _SLATracker:
    def __init__(self, policy: SLAPolicy, *, node_id: str) -> None:
        self.policy = policy
        self.node_id = node_id
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
            phase=phase,
            duration_seconds=elapsed_ms / 1000.0,
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
    "SeamlessDataProvider",
    "SeamlessFetchResult",
    "SeamlessFetchMetadata",
]
