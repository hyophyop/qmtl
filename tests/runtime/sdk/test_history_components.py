from __future__ import annotations

import pytest

from qmtl.runtime.sdk.history_coverage import (
    WarmupWindow,
    compute_missing_ranges,
    ensure_strict_history,
)
from qmtl.runtime.sdk.history_warmup_polling import HistoryWarmupPoller, WarmupRequest


class DummyProvider:
    def __init__(self, coverages: list[list[tuple[int, int]]]) -> None:
        self._coverages = coverages
        self.fill_calls: list[tuple[int, int]] = []

    async def coverage(self, *, node_id: str, interval: int) -> list[tuple[int, int]]:
        if self._coverages:
            return self._coverages.pop(0)
        return []

    async def fill_missing(
        self,
        start: int,
        end: int,
        *,
        node_id: str,
        interval: int,
    ) -> None:
        self.fill_calls.append((start, end))


class AdvancingTime:
    def __init__(self, values: list[float]) -> None:
        self._values = values
        self._index = 0

    def __call__(self) -> float:
        value = self._values[min(self._index, len(self._values) - 1)]
        self._index += 1
        return value


@pytest.mark.asyncio
async def test_poller_times_out_when_deadline_exceeded() -> None:
    provider = DummyProvider(coverages=[[], []])
    time_source = AdvancingTime([0.0, 61.0])
    poller = HistoryWarmupPoller(provider, time_source=time_source)
    window = WarmupWindow(start=0, end=10, interval=10)
    request = WarmupRequest(
        node_id="n1",
        interval=10,
        window=window,
        timeout=60.0,
    )

    result = await poller.poll(request, is_ready=lambda: False)

    assert result.timed_out is True
    assert provider.fill_calls == [(0, 10)]
    assert [(gap.start, gap.end) for gap in result.missing] == [(0, 10)]


def test_missing_ranges_identify_gaps() -> None:
    window = WarmupWindow(start=0, end=50, interval=10)
    coverage = [(0, 10), (40, 50)]

    gaps = compute_missing_ranges(coverage, window)

    assert [(gap.start, gap.end) for gap in gaps] == [(20, 30)]


def test_strict_history_detects_missing_points() -> None:
    timestamps = [0, 10, 30, 40]
    coverage = [(0, 40)]

    with pytest.raises(RuntimeError):
        ensure_strict_history(timestamps, interval=10, required_points=5, coverage=coverage)
