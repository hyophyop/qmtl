from __future__ import annotations

from typing import Protocol, AsyncIterator, Optional, Callable, Awaitable, TypeVar
from abc import ABC
import pandas as pd
from enum import Enum
import asyncio
import logging
import os
import time

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
from .sla import SLAPolicy
from .exceptions import SeamlessSLAExceeded

logger = logging.getLogger(__name__)

"""Seamless Data Provider interfaces for transparent data access with auto-backfill."""

T = TypeVar("T")


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

        # Internal state
        self._active_backfills: dict[str, bool] = {}

    @property
    def last_conformance_report(self) -> Optional[ConformanceReport]:
        """Return the most recent conformance report emitted by ``fetch``."""

        return self._last_conformance_report

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

        if tracker:
            tracker.observe_total()
        return result
    
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
        # Check current availability
        if sla_tracker:
            available_ranges = await sla_tracker.observe_async(
                "storage_wait",
                sla_tracker.policy.max_wait_storage_ms,
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
                raise SeamlessSLAExceeded(
                    "sync_gap",
                    node_id=node_id,
                    elapsed_ms=float(elapsed_ms),
                    budget_ms=int(budget_ms) if interval_ms else None,
                )

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
        if sla_tracker:
            updated_ranges = await sla_tracker.observe_async(
                "storage_wait",
                sla_tracker.policy.max_wait_storage_ms,
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
            if 'ts' in combined.columns:
                combined = combined.sort_values('ts')
            # Run through conformance pipeline if provided (no-op otherwise)
            try:
                if self._conformance:
                    combined, report = self._conformance.normalize(
                        combined,
                        schema=None,
                        interval=interval,
                    )
                    self._last_conformance_report = report
                    sdk_metrics.observe_conformance_report(
                        node_id=node_id,
                        flags=report.flags_counts,
                        warnings=report.warnings,
                    )
                    if (report.warnings or report.flags_counts) and not self._partial_ok:
                        raise ConformancePipelineError(report)
            except ConformancePipelineError:
                raise
            except Exception:  # pragma: no cover - defensive, keep behavior intact
                pass
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

    def _record_phase(self, phase: str, elapsed_ms: float, budget_ms: int | None) -> None:
        sdk_metrics.observe_sla_phase_duration(
            node_id=self.node_id,
            phase=phase,
            duration_seconds=elapsed_ms / 1000.0,
        )
        if budget_ms is not None and elapsed_ms > budget_ms:
            logger.error(
                "seamless.sla.violation",
                extra={
                    "node_id": self.node_id,
                    "phase": phase,
                    "elapsed_ms": elapsed_ms,
                    "budget_ms": budget_ms,
                },
            )
            raise SeamlessSLAExceeded(
                phase,
                node_id=self.node_id,
                elapsed_ms=elapsed_ms,
                budget_ms=budget_ms,
            )


__all__ = [
    "DataAvailabilityStrategy",
    "DataSourcePriority",
    "DataSource",
    "AutoBackfiller",
    "LiveDataFeed",
    "ConformancePipelineError",
    "SeamlessDataProvider",
]
