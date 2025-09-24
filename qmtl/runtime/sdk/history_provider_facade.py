from __future__ import annotations

"""Facade implementations for working with :class:`HistoryBackend`."""

import asyncio
from collections import defaultdict
from typing import Dict, Iterable, List

import pandas as pd

from .data_io import (
    AutoBackfillRequest,
    DataFetcher,
    HistoryBackend,
    HistoryProvider,
)


class AugmentedHistoryProvider(HistoryProvider):
    """Augment a :class:`HistoryBackend` with caching and backfill helpers."""

    def __init__(
        self,
        backend: HistoryBackend,
        *,
        fetcher: DataFetcher | None = None,
    ) -> None:
        self.backend = backend
        self.fetcher = fetcher
        self._coverage_cache: Dict[tuple[str, int], list[tuple[int, int]]] = {}
        self._locks: Dict[tuple[str, int], asyncio.Lock] = defaultdict(asyncio.Lock)

    # ------------------------------------------------------------------
    def bind_stream(self, stream) -> None:  # type: ignore[override]
        super().bind_stream(stream)
        if hasattr(self.backend, "bind_stream"):
            self.backend.bind_stream(stream)  # type: ignore[attr-defined]

    # ------------------------------------------------------------------
    async def fetch(
        self, start: int, end: int, *, node_id: str, interval: int
    ) -> pd.DataFrame:
        key = (node_id, interval)
        inclusive_end = end - interval
        lock = self._locks[key]
        async with lock:
            if inclusive_end >= start:
                await self._prepare_backfill(
                    key,
                    AutoBackfillRequest(
                        node_id=node_id,
                        interval=interval,
                        start=start,
                        end=inclusive_end,
                    ),
                    require_fetcher=False,
                )
            return await self.backend.read_range(
                start, end, node_id=node_id, interval=interval
            )

    # ------------------------------------------------------------------
    async def coverage(
        self, *, node_id: str, interval: int
    ) -> list[tuple[int, int]]:
        key = (node_id, interval)
        lock = self._locks[key]
        async with lock:
            if key not in self._coverage_cache:
                ranges = await self.backend.coverage(
                    node_id=node_id, interval=interval
                )
                self._coverage_cache[key] = self._normalize_ranges(
                    ranges, interval
                )
            return list(self._coverage_cache[key])

    # ------------------------------------------------------------------
    async def fill_missing(
        self, start: int, end: int, *, node_id: str, interval: int
    ) -> None:
        key = (node_id, interval)
        lock = self._locks[key]
        async with lock:
            await self._prepare_backfill(
                key,
                AutoBackfillRequest(
                    node_id=node_id,
                    interval=interval,
                    start=start,
                    end=end,
                ),
                require_fetcher=True,
            )

    # ------------------------------------------------------------------
    async def _prepare_backfill(
        self,
        key: tuple[str, int],
        request: AutoBackfillRequest,
        *,
        require_fetcher: bool,
    ) -> None:
        if request.start > request.end:
            return

        coverage = await self._ensure_coverage(key, request.node_id, request.interval)
        missing = self._missing_windows(coverage, request)
        if not missing:
            return

        if self.fetcher is None:
            if require_fetcher:
                raise RuntimeError("DataFetcher not configured for backfilling")
            return

        updated = coverage
        for window in missing:
            df = await self.fetcher.fetch(
                window.start,
                window.end,
                node_id=window.node_id,
                interval=window.interval,
            )
            if df is None or df.empty:
                continue
            df = df.sort_values("ts")
            df = df[(df["ts"] >= window.start) & (df["ts"] <= window.end)]
            if df.empty:
                continue
            await self.backend.write_rows(
                df, node_id=window.node_id, interval=window.interval
            )
            updated = self._merge_ranges(
                updated,
                self._ranges_from_dataframe(df, window.interval),
                window.interval,
            )

        self._coverage_cache[key] = updated

    # ------------------------------------------------------------------
    async def _ensure_coverage(
        self, key: tuple[str, int], node_id: str, interval: int
    ) -> list[tuple[int, int]]:
        if key not in self._coverage_cache:
            ranges = await self.backend.coverage(node_id=node_id, interval=interval)
            self._coverage_cache[key] = self._normalize_ranges(ranges, interval)
        return list(self._coverage_cache[key])

    # ------------------------------------------------------------------
    def _missing_windows(
        self, coverage: list[tuple[int, int]], request: AutoBackfillRequest
    ) -> list[AutoBackfillRequest]:
        if not coverage:
            return [request]

        interval = request.interval
        sorted_ranges = sorted(coverage, key=lambda r: r[0])
        missing: List[AutoBackfillRequest] = []
        idx = 0
        current_missing_start: int | None = None
        ts = request.start
        while ts <= request.end:
            while idx < len(sorted_ranges) and sorted_ranges[idx][1] < ts:
                idx += 1
            present = False
            if idx < len(sorted_ranges):
                start, end = sorted_ranges[idx]
                present = start <= ts <= end

            if present:
                if current_missing_start is not None:
                    missing.append(
                        AutoBackfillRequest(
                            node_id=request.node_id,
                            interval=interval,
                            start=current_missing_start,
                            end=ts - interval,
                        )
                    )
                    current_missing_start = None
            else:
                if current_missing_start is None:
                    current_missing_start = ts

            ts += interval

        if current_missing_start is not None:
            missing.append(
                AutoBackfillRequest(
                    node_id=request.node_id,
                    interval=interval,
                    start=current_missing_start,
                    end=request.end,
                )
            )

        return [m for m in missing if m.start <= m.end]

    # ------------------------------------------------------------------
    def _ranges_from_dataframe(
        self, df: pd.DataFrame, interval: int
    ) -> list[tuple[int, int]]:
        if "ts" not in df.columns or df.empty:
            return []
        timestamps = sorted(int(ts) for ts in df["ts"].tolist())
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
    def _merge_ranges(
        self,
        existing: list[tuple[int, int]],
        new_ranges: Iterable[tuple[int, int]],
        interval: int,
    ) -> list[tuple[int, int]]:
        combined = sorted(list(existing) + list(new_ranges), key=lambda r: r[0])
        if not combined:
            return []
        merged: List[tuple[int, int]] = [combined[0]]
        for start, end in combined[1:]:
            last_start, last_end = merged[-1]
            if start <= last_end + interval:
                merged[-1] = (last_start, max(last_end, end))
            else:
                merged.append((start, end))
        return merged

    # ------------------------------------------------------------------
    def _normalize_ranges(
        self, ranges: Iterable[tuple[int, int]], interval: int
    ) -> list[tuple[int, int]]:
        return self._merge_ranges([], ranges, interval)


__all__ = ["AugmentedHistoryProvider"]

