from __future__ import annotations

"""Facade implementations for working with :class:`HistoryBackend`."""

import asyncio
from collections import defaultdict
from typing import Dict, Iterable, List

import pandas as pd

from .auto_backfill import AutoBackfillStrategy, FetcherBackfillStrategy
from .data_io import AutoBackfillRequest, DataFetcher, HistoryBackend, HistoryProvider


class AugmentedHistoryProvider(HistoryProvider):
    """Augment a :class:`HistoryBackend` with caching and backfill helpers."""

    def __init__(
        self,
        backend: HistoryBackend,
        *,
        fetcher: DataFetcher | None = None,
        auto_backfill: AutoBackfillStrategy | None = None,
    ) -> None:
        self.backend = backend
        self.fetcher = fetcher
        if auto_backfill is None and fetcher is not None:
            auto_backfill = FetcherBackfillStrategy(fetcher)
        self.auto_backfill = auto_backfill
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
    async def ensure_range(
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
                require_fetcher=False,
            )

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

        strategy = self.auto_backfill
        if strategy is None:
            if require_fetcher:
                raise RuntimeError("Auto backfill strategy not configured")
            return

        await self._ensure_coverage(
            key, request.node_id, request.interval, force_refresh=True
        )
        updated = await strategy.ensure_range(
            request,
            self.backend,
            coverage_cache=self._coverage_cache,
        )
        if updated is None:  # pragma: no cover - defensive
            updated = self._coverage_cache.get(key, [])
        self._coverage_cache[key] = self._normalize_ranges(
            updated, request.interval
        )

    # ------------------------------------------------------------------
    async def _ensure_coverage(
        self,
        key: tuple[str, int],
        node_id: str,
        interval: int,
        *,
        force_refresh: bool = False,
    ) -> list[tuple[int, int]]:
        if force_refresh or key not in self._coverage_cache:
            ranges = await self.backend.coverage(node_id=node_id, interval=interval)
            self._coverage_cache[key] = self._normalize_ranges(ranges, interval)
        return list(self._coverage_cache[key])

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

