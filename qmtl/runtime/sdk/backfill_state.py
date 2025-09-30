from __future__ import annotations

"""Simple tracking for backfill progress."""

from collections import defaultdict
from typing import Iterable


class BackfillState:
    """Record completed timestamp ranges for ``(upstream, interval)`` pairs."""

    def __init__(self) -> None:
        self._ranges: dict[tuple[str, int], list[tuple[int, int]]] = defaultdict(list)

    # --------------------------------------------------------------
    def _merge(self, ranges: list[tuple[int, int]], interval: int) -> list[tuple[int, int]]:
        if not ranges:
            return []
        ranges.sort()
        merged: list[tuple[int, int]] = [ranges[0]]
        for start, end in ranges[1:]:
            last_start, last_end = merged[-1]
            if start <= last_end + interval:
                merged[-1] = (last_start, max(last_end, end))
            else:
                merged.append((start, end))
        return merged

    def mark_range(self, upstream: str, interval: int, start: int, end: int) -> None:
        """Mark ``[start, end]`` (inclusive) as backfilled."""
        if start > end:
            start, end = end, start
        key = (upstream, interval)
        ranges = self._ranges[key]
        ranges.append((start, end))
        self._ranges[key] = self._merge(ranges, interval)

    def mark_ranges(self, upstream: str, interval: int, rng: Iterable[tuple[int, int]]) -> None:
        for start, end in rng:
            self.mark_range(upstream, interval, start, end)

    def ranges(self, upstream: str, interval: int) -> list[tuple[int, int]]:
        """Return list of completed ranges for ``(upstream, interval)``."""
        return list(self._ranges.get((upstream, interval), []))

    def is_complete(self, upstream: str, interval: int, start: int, end: int) -> bool:
        """Check if ``[start, end]`` is fully completed."""
        for s, e in self._ranges.get((upstream, interval), []):
            if start >= s and end <= e:
                return True
        return False
