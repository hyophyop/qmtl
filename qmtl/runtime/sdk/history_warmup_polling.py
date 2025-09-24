from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Iterable, Protocol

from .history_coverage import CoverageRange, WarmupWindow, compute_missing_ranges


class HistoryProviderProtocol(Protocol):
    async def coverage(self, *, node_id: str, interval: int) -> Iterable[tuple[int, int]]: ...

    async def fill_missing(
        self,
        start: int,
        end: int,
        *,
        node_id: str,
        interval: int,
    ) -> None: ...


@dataclass(frozen=True)
class WarmupRequest:
    node_id: str
    interval: int
    window: WarmupWindow
    stop_on_ready: bool = False
    timeout: float = 60.0


@dataclass(frozen=True)
class WarmupResult:
    coverage: list[tuple[int, int]]
    missing: list[CoverageRange]
    timed_out: bool


class HistoryWarmupPoller:
    """Polling state machine coordinating history provider backfills."""

    def __init__(
        self,
        provider: HistoryProviderProtocol,
        *,
        time_source: Callable[[], float] | None = None,
    ) -> None:
        self._provider = provider
        self._time_source = time_source or time.monotonic

    async def poll(
        self,
        request: WarmupRequest,
        *,
        is_ready: Callable[[], bool],
    ) -> WarmupResult:
        deadline = self._time_source() + request.timeout
        coverage_list = list(
            await self._provider.coverage(node_id=request.node_id, interval=request.interval)
        )
        missing = compute_missing_ranges(coverage_list, request.window)
        timed_out = False

        ensure_range = getattr(self._provider, "ensure_range", None)
        if callable(ensure_range):
            if missing and not is_ready():
                await ensure_range(
                    request.window.start,
                    request.window.end,
                    node_id=request.node_id,
                    interval=request.interval,
                )
                coverage_list = list(
                    await self._provider.coverage(
                        node_id=request.node_id, interval=request.interval
                    )
                )
                missing = compute_missing_ranges(coverage_list, request.window)
            return WarmupResult(coverage=coverage_list, missing=missing, timed_out=timed_out)

        while not is_ready() and missing:
            for gap in missing:
                await self._provider.fill_missing(
                    gap.start,
                    gap.end,
                    node_id=request.node_id,
                    interval=request.interval,
                )
                if request.stop_on_ready and is_ready():
                    break
            if request.stop_on_ready:
                break
            if self._time_source() > deadline:
                timed_out = True
                break
            coverage_list = list(
                await self._provider.coverage(
                    node_id=request.node_id, interval=request.interval
                )
            )
            missing = compute_missing_ranges(coverage_list, request.window)

        return WarmupResult(coverage=coverage_list, missing=missing, timed_out=timed_out)


__all__ = ["HistoryWarmupPoller", "WarmupRequest", "WarmupResult", "HistoryProviderProtocol"]
