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
        coverage_list, missing = await self._refresh_missing(request)
        missing = await self._maybe_ensure_range(request, missing, is_ready)
        timed_out = False

        while missing and not is_ready():
            coverage_list, missing, timed_out = await self._fill_missing_once(
                request, missing, is_ready, deadline
            )
            if timed_out or (request.stop_on_ready and is_ready()):
                break

        return WarmupResult(coverage=coverage_list, missing=missing, timed_out=timed_out)

    async def _refresh_missing(
        self, request: WarmupRequest
    ) -> tuple[list[tuple[int, int]], list[CoverageRange]]:
        coverage_list = list(
            await self._provider.coverage(node_id=request.node_id, interval=request.interval)
        )
        missing = compute_missing_ranges(coverage_list, request.window)
        return coverage_list, missing

    async def _maybe_ensure_range(
        self,
        request: WarmupRequest,
        missing: list[CoverageRange],
        is_ready: Callable[[], bool],
    ) -> list[CoverageRange]:
        ensure_range = getattr(self._provider, "ensure_range", None)
        if not (callable(ensure_range) and missing and not is_ready()):
            return missing

        await ensure_range(
            request.window.start,
            request.window.end,
            node_id=request.node_id,
            interval=request.interval,
        )
        _, new_missing = await self._refresh_missing(request)
        return new_missing

    async def _fill_missing_once(
        self,
        request: WarmupRequest,
        missing: list[CoverageRange],
        is_ready: Callable[[], bool],
        deadline: float,
    ) -> tuple[list[tuple[int, int]], list[CoverageRange], bool]:
        for gap in missing:
            await self._provider.fill_missing(
                gap.start,
                gap.end,
                node_id=request.node_id,
                interval=request.interval,
            )
            if request.stop_on_ready and is_ready():
                break

        timed_out = self._time_source() > deadline
        coverage_list, new_missing = await self._refresh_missing(request)
        return coverage_list, new_missing, timed_out


__all__ = ["HistoryWarmupPoller", "WarmupRequest", "WarmupResult", "HistoryProviderProtocol"]
