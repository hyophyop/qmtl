from __future__ import annotations

from typing import Protocol, AsyncIterator, Optional, Callable
from abc import ABC
import pandas as pd
from enum import Enum
import asyncio
import logging

from .history_coverage import (
    merge_coverage as _merge_coverage,
    compute_missing_ranges as _compute_missing_ranges,
    WarmupWindow,
)
from . import metrics as sdk_metrics

logger = logging.getLogger(__name__)

"""Seamless Data Provider interfaces for transparent data access with auto-backfill."""


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
    ) -> None:
        self.strategy = strategy
        self.cache_source = cache_source
        self.storage_source = storage_source
        self.backfiller = backfiller
        self.live_feed = live_feed
        self.max_backfill_chunk_size = max_backfill_chunk_size
        self.enable_background_backfill = enable_background_backfill
        
        # Internal state
        self._active_backfills: dict[str, bool] = {}
    
    async def fetch(
        self, start: int, end: int, *, node_id: str, interval: int
    ) -> pd.DataFrame:
        """
        Fetch data transparently from available sources.
        
        Implementation follows the priority order and strategy configuration.
        """
        if self.strategy == DataAvailabilityStrategy.FAIL_FAST:
            return await self._fetch_fail_fast(start, end, node_id=node_id, interval=interval)
        elif self.strategy == DataAvailabilityStrategy.AUTO_BACKFILL:
            return await self._fetch_auto_backfill(start, end, node_id=node_id, interval=interval)
        elif self.strategy == DataAvailabilityStrategy.PARTIAL_FILL:
            return await self._fetch_partial_fill(start, end, node_id=node_id, interval=interval)
        else:  # SEAMLESS
            return await self._fetch_seamless(start, end, node_id=node_id, interval=interval)
    
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
            except Exception:
                continue  # Skip failed sources
        
        # Merge overlapping ranges with interval-aware semantics
        try:
            merged = _merge_coverage(all_ranges, interval)
            return [(r.start, r.end) for r in merged]
        except Exception:
            # Fallback to simple merge if utilities are unavailable
            return self._merge_ranges(all_ranges)
    
    async def ensure_data_available(
        self, start: int, end: int, *, node_id: str, interval: int
    ) -> bool:
        """
        Ensure data is available for the given range.
        
        If data is missing and auto-backfill is enabled, trigger backfill.
        Returns True if data will be available after this call.
        """
        # Check current availability
        available_ranges = await self.coverage(node_id=node_id, interval=interval)
        missing_ranges = self._find_missing_ranges(start, end, available_ranges, interval)
        
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
                            missing_start, missing_end, node_id=node_id, interval=interval
                        )
                    else:
                        try:
                            sdk_metrics.observe_backfill_start(node_id, interval)
                            await self.backfiller.backfill(
                                missing_start, missing_end,
                                node_id=node_id, interval=interval,
                                target_storage=self.storage_source,
                            )
                            sdk_metrics.observe_backfill_complete(
                                node_id, interval, missing_end
                            )
                        except Exception:
                            sdk_metrics.observe_backfill_failure(node_id, interval)
                            raise
        
        # Re-check availability
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
        self, start: int, end: int, *, node_id: str, interval: int
    ) -> pd.DataFrame:
        """Implement seamless fetching strategy."""
        # Try each source in priority order
        result_frames = []
        remaining_ranges = [(start, end)]
        
        for source in self._get_ordered_sources():
            if not remaining_ranges:
                break
                
            new_remaining = []
            for range_start, range_end in remaining_ranges:
                try:
                    # Check what this source can provide
                    source_coverage = await source.coverage(node_id=node_id, interval=interval)
                    available_in_range = self._intersect_ranges(
                        [(range_start, range_end)], source_coverage
                    )
                    
                    if available_in_range:
                        # Fetch available data from this source
                        for avail_start, avail_end in available_in_range:
                            frame = await source.fetch(
                                avail_start, avail_end, node_id=node_id, interval=interval
                            )
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
                except Exception:
                    # If source fails, keep the range for other sources
                    new_remaining.append((range_start, range_end))
            
            remaining_ranges = new_remaining
        
        # Try auto-backfill for remaining ranges
        if remaining_ranges and self.backfiller:
            for range_start, range_end in remaining_ranges:
                try:
                    sdk_metrics.observe_backfill_start(node_id, interval)
                    backfilled = await self.backfiller.backfill(
                        range_start, range_end,
                        node_id=node_id, interval=interval,
                        target_storage=self.storage_source
                    )
                    if not backfilled.empty:
                        result_frames.append(backfilled)
                    sdk_metrics.observe_backfill_complete(node_id, interval, range_end)
                except Exception:
                    sdk_metrics.observe_backfill_failure(node_id, interval)
                    continue
        
        # Combine all frames and sort by timestamp
        if result_frames:
            combined = pd.concat(result_frames, ignore_index=True)
            if 'ts' in combined.columns:
                combined = combined.sort_values('ts')
            return combined
        
        return pd.DataFrame()
    
    async def _fetch_fail_fast(
        self, start: int, end: int, *, node_id: str, interval: int
    ) -> pd.DataFrame:
        """Fail fast strategy - only use existing data."""
        for source in self._get_ordered_sources():
            try:
                available = await source.is_available(
                    start, end, node_id=node_id, interval=interval
                )
                if available:
                    return await source.fetch(start, end, node_id=node_id, interval=interval)
            except Exception:
                continue
        
        raise RuntimeError(f"No data available for range [{start}, {end}] in fail-fast mode")
    
    async def _fetch_auto_backfill(
        self, start: int, end: int, *, node_id: str, interval: int
    ) -> pd.DataFrame:
        """Auto-backfill strategy - ensure data is backfilled before returning."""
        await self.ensure_data_available(start, end, node_id=node_id, interval=interval)
        return await self._fetch_seamless(start, end, node_id=node_id, interval=interval)
    
    async def _fetch_partial_fill(
        self, start: int, end: int, *, node_id: str, interval: int
    ) -> pd.DataFrame:
        """Partial fill strategy - return what's available, backfill in background."""
        # Start background backfill but don't wait
        if self.backfiller:
            await self._start_background_backfill(start, end, node_id=node_id, interval=interval)
        
        # Return what's currently available
        return await self._fetch_seamless(start, end, node_id=node_id, interval=interval)
    
    async def _start_background_backfill(
        self, start: int, end: int, *, node_id: str, interval: int
    ) -> None:
        """Start background backfill task with single-flight de-duplication."""
        key = f"{node_id}:{interval}:{start}:{end}"
        if self._active_backfills.get(key):
            return
        self._active_backfills[key] = True

        async def _run() -> None:
            try:
                if not self.backfiller:
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
            except Exception:
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

        # Convert inclusive ranges to half-open to avoid duplicate boundary bars
        result: list[tuple[int, int]] = [
            (start, end + interval) for start, end in from_ranges
        ]
        subtract_half_open = [
            (sub_start, sub_end + interval) for sub_start, sub_end in subtract_ranges
        ]

        for sub_start, sub_end in subtract_half_open:
            new_result: list[tuple[int, int]] = []
            for start, end in result:
                if sub_end <= start or sub_start >= end:
                    new_result.append((start, end))
                else:
                    if start < sub_start:
                        new_result.append((start, sub_start))
                    if end > sub_end:
                        new_result.append((sub_end, end))
            result = new_result

        adjusted: list[tuple[int, int]] = []
        for start, end in result:
            inclusive_end = end - interval
            if inclusive_end >= start:
                adjusted.append((start, inclusive_end))

        return self._merge_ranges(adjusted)


__all__ = [
    "DataAvailabilityStrategy",
    "DataSourcePriority", 
    "DataSource",
    "AutoBackfiller",
    "LiveDataFeed",
    "SeamlessDataProvider",
]
