from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Sequence

from .cache_ring_buffer import RingBuffer


@dataclass(frozen=True)
class BackfillMergeResult:
    """Result of merging historical items into a :class:`RingBuffer`."""

    bucketed_items: list[tuple[int, Any]]
    ranges: list[tuple[int, int]]
    merged_items: list[tuple[int, Any]]


class BackfillMerger:
    """Merge helper for :meth:`NodeCache.backfill_bulk`."""

    def __init__(self, period: int) -> None:
        self._period = period

    def _bucketize(self, interval: int, items: Iterable[tuple[int, Any]]) -> list[tuple[int, Any]]:
        bucketed: list[tuple[int, Any]] = []
        for ts, payload in items:
            bucket = ts - (ts % interval)
            bucketed.append((bucket, payload))
        return bucketed

    def _ranges(self, interval: int, bucketed: Sequence[tuple[int, Any]]) -> list[tuple[int, int]]:
        if not bucketed:
            return []
        ranges: list[tuple[int, int]] = []
        start = bucketed[0][0]
        prev = start
        for ts, _ in bucketed[1:]:
            if ts == prev + interval:
                prev = ts
            else:
                ranges.append((start, prev))
                start = ts
                prev = ts
        ranges.append((start, prev))
        return ranges

    def merge(
        self,
        buffer: RingBuffer,
        interval: int,
        items: Iterable[tuple[int, Any]],
    ) -> BackfillMergeResult:
        bucketed = self._bucketize(interval, items)
        ranges = self._ranges(interval, bucketed)

        existing = {ts: payload for ts, payload in buffer.items()}
        merged = dict(existing)
        for ts, payload in bucketed:
            merged.setdefault(ts, payload)

        merged_items = sorted(merged.items())[-self._period :]
        return BackfillMergeResult(bucketed, ranges, merged_items)


__all__ = ["BackfillMerger", "BackfillMergeResult"]
