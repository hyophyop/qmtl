from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence


@dataclass(frozen=True)
class CoverageRange:
    start: int
    end: int


@dataclass(frozen=True)
class WarmupWindow:
    start: int
    end: int
    interval: int


def merge_coverage(coverage: Iterable[tuple[int, int]], interval: int) -> list[CoverageRange]:
    ranges = sorted((int(s), int(e)) for s, e in coverage)
    merged: list[CoverageRange] = []
    for start, end in ranges:
        if not merged:
            merged.append(CoverageRange(start, end))
            continue
        last = merged[-1]
        if start <= last.end + interval:
            merged[-1] = CoverageRange(last.start, max(last.end, end))
        else:
            merged.append(CoverageRange(start, end))
    return merged


def compute_missing_ranges(
    coverage: Iterable[tuple[int, int]] | None,
    window: WarmupWindow,
) -> list[CoverageRange]:
    if window.start is None or window.end is None:
        return []
    merged = merge_coverage(coverage or [], window.interval)
    gaps: list[CoverageRange] = []
    cursor = window.start
    for rng in merged:
        if rng.end < window.start:
            continue
        if rng.start > window.end:
            break
        if rng.start > cursor:
            gaps.append(
                CoverageRange(cursor, min(rng.start - window.interval, window.end))
            )
        cursor = max(cursor, rng.end + window.interval)
        if cursor > window.end:
            break
    if cursor <= window.end:
        gaps.append(CoverageRange(cursor, window.end))
    return [gap for gap in gaps if gap.start <= gap.end]


def coverage_bounds(coverage: Iterable[tuple[int, int]] | None) -> CoverageRange | None:
    if not coverage:
        return None
    starts, ends = zip(*coverage)
    return CoverageRange(min(int(s) for s in starts), max(int(e) for e in ends))


def ensure_strict_history(
    timestamps: Sequence[int],
    interval: int | None,
    required_points: int | None,
    coverage: Iterable[tuple[int, int]] | None,
) -> None:
    required = (required_points or 1) if required_points is not None else 1
    if not timestamps:
        raise RuntimeError("history missing in strict mode")

    if coverage:
        bounds = coverage_bounds(coverage)
        if bounds and interval:
            expected = int((bounds.end - bounds.start) // interval) + 1
            actual = sum(1 for ts in timestamps if bounds.start <= ts <= bounds.end)
            if actual < expected:
                raise RuntimeError("history gap detected in strict mode")
    elif interval:
        for a, b in zip(timestamps, timestamps[1:]):
            if (b - a) != interval:
                raise RuntimeError("history gap detected in strict mode")

    if len(timestamps) < required:
        raise RuntimeError("history missing in strict mode")


__all__ = [
    "CoverageRange",
    "WarmupWindow",
    "merge_coverage",
    "compute_missing_ranges",
    "coverage_bounds",
    "ensure_strict_history",
]
