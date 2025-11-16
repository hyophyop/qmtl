from __future__ import annotations

import asyncio
from typing import List, Tuple

import sys
import types


def _sanitize_sys_modules() -> None:
    """Replace unhashable module stubs with lightweight module objects."""

    for name, module in list(sys.modules.items()):
        try:
            hash(module)
        except TypeError:
            replacement = types.ModuleType(name)
            replacement.__dict__.update(getattr(module, "__dict__", {}))
            sys.modules[name] = replacement


_sanitize_sys_modules()
from hypothesis import given, settings
from hypothesis import strategies as st

from qmtl.runtime.sdk.history_coverage import WarmupWindow, compute_missing_ranges, merge_coverage
from qmtl.runtime.sdk.seamless_data_provider import SeamlessDataProvider, _RangeOperations


def _range_strategy() -> st.SearchStrategy[List[Tuple[int, int]]]:
    return st.lists(
        st.builds(
            lambda a, b: (min(a, b), max(a, b)),
            st.integers(min_value=-1_000, max_value=1_000),
            st.integers(min_value=-1_000, max_value=1_000),
        ),
        max_size=8,
    )


def _interval_strategy() -> st.SearchStrategy[int]:
    return st.integers(min_value=1, max_value=60)


def _warmup_window_strategy() -> st.SearchStrategy[WarmupWindow]:
    return st.builds(
        lambda a, b, interval: WarmupWindow(
            start=min(a, b), end=max(a, b), interval=interval
        ),
        st.integers(min_value=-1_000, max_value=1_000),
        st.integers(min_value=-1_000, max_value=1_000),
        _interval_strategy(),
    )


class _PropertyProvider(SeamlessDataProvider):
    """Concrete SeamlessDataProvider for property-based testing."""

    pass


@settings(deadline=None, max_examples=200)
@given(ranges=_range_strategy(), interval=_interval_strategy())
def test_merge_coverage_preserves_discrete_union(
    ranges: list[tuple[int, int]], interval: int
) -> None:
    _sanitize_sys_modules()
    merged = merge_coverage(ranges, interval)

    # All merged ranges are monotonically ordered and non-overlapping on the grid.
    for idx in range(len(merged)):
        current = merged[idx]
        assert current.start <= current.end
        if idx:
            previous = merged[idx - 1]
            assert current.start > previous.end + interval

    for start, end in ranges:
        if start > end:
            continue
        assert any(r.start <= start and r.end >= end for r in merged)


@settings(deadline=None, max_examples=200)
@given(
    ranges=_range_strategy(),
    window=_warmup_window_strategy(),
)
def test_compute_missing_ranges_partitions_window(
    ranges: list[tuple[int, int]], window: WarmupWindow
) -> None:
    _sanitize_sys_modules()
    missing = compute_missing_ranges(ranges, window)

    # Missing ranges are disjoint and within the window.
    for gap in missing:
        assert window.start <= gap.start <= gap.end <= window.end
    for prev, cur in zip(missing, missing[1:]):
        assert cur.start > prev.end

    available_ranges = merge_coverage(ranges, window.interval)
    for gap in missing:
        for rng in available_ranges:
            assert not (gap.start <= rng.end and gap.end >= rng.start)


@settings(deadline=None, max_examples=200)
@given(
    ranges=_range_strategy(),
    window=_warmup_window_strategy(),
)
def test_find_missing_ranges_matches_history_utilities(
    ranges: list[tuple[int, int]], window: WarmupWindow
) -> None:
    _sanitize_sys_modules()
    provider = _PropertyProvider()

    expected = [(gap.start, gap.end) for gap in compute_missing_ranges(ranges, window)]

    async def fake_coverage(*, node_id: str, interval: int) -> list[tuple[int, int]]:
        assert node_id == "node"
        assert interval == window.interval
        return list(ranges)

    class DummyBackfiller:
        def __init__(self) -> None:
            self.calls: list[tuple[int, int]] = []

        async def can_backfill(
            self, start: int, end: int, *, node_id: str, interval: int
        ) -> bool:
            assert node_id == "node"
            assert interval == window.interval
            self.calls.append((start, end))
            return False

    dummy_backfiller = DummyBackfiller()
    provider.coverage = fake_coverage
    provider.backfiller = dummy_backfiller

    result = asyncio.run(
        provider.ensure_data_available(
            window.start,
            window.end,
            node_id="node",
            interval=window.interval,
        )
    )

    assert dummy_backfiller.calls == expected
    assert result == (len(expected) == 0)


def test_subtract_segment_skips_unaligned_ranges() -> None:
    segments = [(0, 20)]
    result = _RangeOperations._subtract_segment(segments, sub_start=3, sub_end=10, interval=5)
    assert result == segments


def test_subtract_segment_splits_segment_on_grid() -> None:
    segments = [(0, 20)]
    result = _RangeOperations._subtract_segment(segments, sub_start=5, sub_end=10, interval=5)
    assert result == [(0, 0), (15, 20)]
