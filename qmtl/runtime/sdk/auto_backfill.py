from __future__ import annotations

"""Auto backfill strategies for history providers."""

from abc import ABC, abstractmethod
import time
from collections.abc import Awaitable, Callable, Iterable, MutableMapping
from typing import Any, TYPE_CHECKING, NamedTuple

import polars as pl

from .data_io import AutoBackfillRequest, DataFetcher, HistoryBackend
from .history_coverage import CoverageRange, WarmupWindow, compute_missing_ranges
from . import metrics

if TYPE_CHECKING:  # pragma: no cover - optional dependency
    from .event_service import EventRecorderService

CoverageCache = MutableMapping[tuple[str, int], list[tuple[int, int]]]
ReplayEvent = tuple[int, Any]
ReplaySource = Callable[[int, int, str, int], Awaitable[Iterable[ReplayEvent]]]


class AutoBackfillStrategy(ABC):
    """Base interface for auto backfill helpers."""

    metric_name: str = "auto_backfill"

    @abstractmethod
    async def ensure_range(
        self,
        request: AutoBackfillRequest,
        backend: HistoryBackend,
        *,
        coverage_cache: CoverageCache,
    ) -> list[tuple[int, int]]:
        """Ensure ``backend`` covers ``request``.

        Implementations must return the updated, normalized coverage ranges for
        ``(node_id, interval)`` after the operation. ``coverage_cache`` is shared
        between requests and can be updated in-place if desired.
        """

    # ------------------------------------------------------------------
    def _metric_labels(self, request: AutoBackfillRequest) -> dict[str, str]:
        return {
            "strategy": self.metric_name,
            "node_id": str(request.node_id),
            "interval": str(request.interval),
        }

    def _metric_key(self, request: AutoBackfillRequest) -> tuple[str, str, str]:
        return (
            self.metric_name,
            str(request.node_id),
            str(request.interval),
        )

    def _inc_counter(
        self,
        counter,
        request: AutoBackfillRequest,
        amount: int | float = 1,
    ) -> None:
        if amount <= 0:
            return
        labels = self._metric_labels(request)
        counter.labels(**labels).inc(amount)
        if hasattr(counter, "_vals"):
            key = self._metric_key(request)
            counter._vals[key] = counter._vals.get(key, 0) + amount

    def _observe_duration(self, started_at: float) -> None:
        duration_ms = (time.perf_counter() - started_at) * 1000.0
        histogram = metrics.history_auto_backfill_duration_ms
        histogram.labels(strategy=self.metric_name).observe(duration_ms)
        if hasattr(histogram, "_vals"):
            histogram._vals.setdefault(self.metric_name, []).append(duration_ms)

    # ------------------------------------------------------------------
    @staticmethod
    def _merge_ranges(
        existing: Iterable[tuple[int, int]],
        new_ranges: Iterable[tuple[int, int]],
        interval: int,
    ) -> list[tuple[int, int]]:
        combined = sorted(list(existing) + list(new_ranges), key=lambda r: r[0])
        if not combined:
            return []
        merged: list[tuple[int, int]] = [combined[0]]
        for start, end in combined[1:]:
            last_start, last_end = merged[-1]
            if start <= last_end + interval:
                merged[-1] = (last_start, max(last_end, end))
            else:
                merged.append((start, end))
        return merged

    # ------------------------------------------------------------------
    @staticmethod
    def _ranges_from_dataframe(df: pl.DataFrame, interval: int) -> list[tuple[int, int]]:
        if "ts" not in df.columns or df.is_empty():
            return []
        timestamps = sorted(int(ts) for ts in df.get_column("ts").to_list())
        if not timestamps:
            return []
        ranges: list[tuple[int, int]] = []
        start = prev = timestamps[0]
        for ts in timestamps[1:]:
            if ts == prev + interval:
                prev = ts
            else:
                ranges.append((start, prev))
                start = prev = ts
        ranges.append((start, prev))
        return ranges

    # ------------------------------------------------------------------
    @staticmethod
    def _drop_existing(
        frame: pl.DataFrame,
        existing: pl.DataFrame | None,
    ) -> tuple[pl.DataFrame, bool]:
        if existing is None or existing.is_empty() or "ts" not in existing.columns:
            return frame, False
        existing_ts = {int(ts) for ts in existing.get_column("ts").to_list()}
        if not existing_ts:
            return frame, False
        before = frame.height
        filtered = frame.filter(~pl.col("ts").is_in(list(existing_ts)))
        return filtered, filtered.height != before

    # ------------------------------------------------------------------
    @staticmethod
    def _normalize_frame(
        frame: pl.DataFrame | None, start: int, end: int
    ) -> pl.DataFrame:
        if frame is None or frame.is_empty():
            return pl.DataFrame()
        if "ts" not in frame.columns:
            raise KeyError("DataFetcher returned frame without 'ts' column")
        df = frame.clone()
        df = df.with_columns(pl.col("ts").cast(pl.Int64, strict=False))
        df = df.sort("ts")
        return df.filter((pl.col("ts") >= start) & (pl.col("ts") <= end))


class FetcherBackfillStrategy(AutoBackfillStrategy):
    """Backfill missing ranges using a :class:`DataFetcher`."""

    metric_name = "fetcher"

    def __init__(self, fetcher: DataFetcher) -> None:
        self.fetcher = fetcher

    async def ensure_range(
        self,
        request: AutoBackfillRequest,
        backend: HistoryBackend,
        *,
        coverage_cache: CoverageCache,
    ) -> list[tuple[int, int]]:
        self._inc_counter(metrics.history_auto_backfill_requests_total, request)
        started_at = time.perf_counter()

        key = (request.node_id, request.interval)
        coverage = list(coverage_cache.get(key, []))
        window = WarmupWindow(
            start=request.start, end=request.end, interval=request.interval
        )
        missing = compute_missing_ranges(coverage, window)
        self._inc_counter(
            metrics.history_auto_backfill_missing_ranges_total,
            request,
            len(missing),
        )
        if not missing:
            self._observe_duration(started_at)
            return coverage

        refresh_post_write = False
        updated = coverage
        rows_written = 0
        for gap in missing:
            frame = await self.fetcher.fetch(
                gap.start,
                gap.end,
                node_id=request.node_id,
                interval=request.interval,
            )
            normalized = self._normalize_frame(frame, gap.start, gap.end)
            if normalized.is_empty():
                continue

            existing = await backend.read_range(
                gap.start,
                gap.end + request.interval,
                node_id=request.node_id,
                interval=request.interval,
            )
            normalized, refreshed = self._drop_existing(normalized, existing)
            refresh_post_write = refresh_post_write or refreshed
            if normalized.is_empty():
                continue

            await backend.write_rows(
                normalized, node_id=request.node_id, interval=request.interval
            )
            rows_written += normalized.height
            updated = self._merge_ranges(
                updated,
                self._ranges_from_dataframe(normalized, request.interval),
                request.interval,
            )

        if refresh_post_write:
            refreshed_ranges = await backend.coverage(
                node_id=request.node_id, interval=request.interval
            )
            updated = self._merge_ranges([], refreshed_ranges, request.interval)

        coverage_cache[key] = updated
        if rows_written:
            self._inc_counter(
                metrics.history_auto_backfill_rows_total,
                request,
                rows_written,
            )
        self._observe_duration(started_at)
        return list(updated)

class LiveReplayBackfillStrategy(AutoBackfillStrategy):
    """Recreate missing history from live event buffers or recorders."""

    metric_name = "live_replay"

    def __init__(
        self,
        *,
        event_service: EventRecorderService | None = None,
        replay_source: ReplaySource | None = None,
        normalizer: Callable[[Iterable[ReplayEvent]], pl.DataFrame] | None = None,
    ) -> None:
        if event_service is None and replay_source is None:
            raise ValueError(
                "event_service or replay_source must be provided for live replay"
            )
        self._event_service = event_service
        self._replay_source = replay_source
        self._normalizer = normalizer or self._default_normalizer

    async def ensure_range(
        self,
        request: AutoBackfillRequest,
        backend: HistoryBackend,
        *,
        coverage_cache: CoverageCache,
    ) -> list[tuple[int, int]]:
        self._inc_counter(metrics.history_auto_backfill_requests_total, request)
        started_at = time.perf_counter()

        key = (request.node_id, request.interval)
        coverage = list(coverage_cache.get(key, []))
        window = WarmupWindow(
            start=request.start, end=request.end, interval=request.interval
        )
        missing = compute_missing_ranges(coverage, window)
        self._inc_counter(
            metrics.history_auto_backfill_missing_ranges_total,
            request,
            len(missing),
        )
        if not missing:
            self._observe_duration(started_at)
            return coverage

        gap_results = await self._fill_missing_gaps(missing, request, backend)
        updated = coverage
        rows_written = 0
        refresh_post_write = False

        for result in gap_results:
            if not result.ranges:
                continue
            refresh_post_write = refresh_post_write or result.refresh
            rows_written += result.rows_written
            updated = self._merge_ranges(updated, result.ranges, request.interval)

        if refresh_post_write:
            refreshed_ranges = await backend.coverage(
                node_id=request.node_id, interval=request.interval
            )
            updated = self._merge_ranges([], refreshed_ranges, request.interval)

        coverage_cache[key] = updated
        if rows_written:
            self._inc_counter(
                metrics.history_auto_backfill_rows_total,
                request,
                rows_written,
            )
        self._observe_duration(started_at)
        return list(updated)

    async def _fill_missing_gaps(
        self,
        missing: Iterable[CoverageRange],
        request: AutoBackfillRequest,
        backend: HistoryBackend,
    ) -> list["_GapResult"]:
        results: list["_GapResult"] = []
        for gap in missing:
            result = await self._process_gap(gap, request, backend)
            results.append(result)
        return results

    async def _process_gap(
        self,
        gap: CoverageRange,
        request: AutoBackfillRequest,
        backend: HistoryBackend,
    ) -> "_GapResult":
        events = await self._collect_events(
            gap.start, gap.end, request.node_id, request.interval
        )
        frame = self._normalize_frame(self._normalizer(events), gap.start, gap.end)
        if frame is None or frame.is_empty():
            return _GapResult(ranges=[], rows_written=0, refresh=False)

        existing = await backend.read_range(
            gap.start,
            gap.end + request.interval,
            node_id=request.node_id,
            interval=request.interval,
        )
        frame, refreshed = self._drop_existing(frame, existing)
        if frame.is_empty():
            return _GapResult(ranges=[], rows_written=0, refresh=refreshed)

        await backend.write_rows(
            frame, node_id=request.node_id, interval=request.interval
        )
        ranges = self._ranges_from_dataframe(frame, request.interval)
        return _GapResult(ranges=ranges, rows_written=frame.height, refresh=refreshed)

    # ------------------------------------------------------------------
    async def _collect_events(
        self, start: int, end: int, node_id: str, interval: int
    ) -> list[ReplayEvent]:
        if self._replay_source is not None:
            return await self._collect_from_replay_source(start, end, node_id, interval)

        recorder = getattr(self._event_service, "recorder", None)
        if recorder is None:
            return []

        events = await self._collect_from_recorder(recorder, start, end, node_id, interval)
        if events:
            return events
        return self._collect_from_buffer(recorder, start, end)

    async def _collect_from_replay_source(
        self, start: int, end: int, node_id: str, interval: int
    ) -> list[ReplayEvent]:
        result = await self._replay_source(start, end, node_id, interval)  # type: ignore[misc]
        return list(result)

    async def _collect_from_recorder(
        self, recorder: Any, start: int, end: int, node_id: str, interval: int
    ) -> list[ReplayEvent]:
        replay_fn = getattr(recorder, "replay", None)
        if callable(replay_fn):
            result = await replay_fn(start, end, node_id=node_id, interval=interval)
            return list(result)

        read_fn = getattr(recorder, "read_range", None)
        if callable(read_fn):
            result = await read_fn(start, end, node_id=node_id, interval=interval)
            if isinstance(result, pl.DataFrame):
                return [
                    (int(row["ts"]), {k: row[k] for k in row.keys() if k != "ts"})
                    for row in result.iter_rows(named=True)
                ]
            return list(result)
        return []

    def _collect_from_buffer(self, recorder: Any, start: int, end: int) -> list[ReplayEvent]:
        buffer_attr = getattr(recorder, "buffer", None)
        if buffer_attr is None:
            return []
        events: list[ReplayEvent] = []
        for ts, payload in getattr(buffer_attr, "items", lambda: buffer_attr)():
            if start <= ts <= end:
                events.append((int(ts), payload))
        return events

    # ------------------------------------------------------------------
    @staticmethod
    def _default_normalizer(events: Iterable[ReplayEvent]) -> pl.DataFrame:
        records = []
        for ts, payload in events:
            record: dict[str, Any] = {"ts": int(ts)}
            if isinstance(payload, pl.Series):
                if payload.name:
                    values = payload.to_list()
                    record[payload.name] = values[0] if len(values) == 1 else values
                else:
                    record["value"] = payload.to_list()
            elif isinstance(payload, pl.DataFrame):
                # Flatten DataFrame by taking first row per event
                if not payload.is_empty():
                    record.update({str(key): value for key, value in payload.row(0, named=True).items()})
            elif isinstance(payload, dict):
                record.update({str(key): value for key, value in payload.items()})
            else:
                record["value"] = payload
            records.append(record)
        return pl.DataFrame(records)


__all__ = [
    "AutoBackfillStrategy",
    "FetcherBackfillStrategy",
    "LiveReplayBackfillStrategy",
    "CoverageCache",
    "ReplayEvent",
    "ReplaySource",
]


class _GapResult(NamedTuple):
    ranges: list[tuple[int, int]]
    rows_written: int
    refresh: bool
