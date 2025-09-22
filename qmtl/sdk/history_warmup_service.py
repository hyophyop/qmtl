from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any

from .history_coverage import (
    WarmupWindow,
    compute_missing_ranges,
    coverage_bounds,
    ensure_strict_history,
)
from .history_loader import HistoryLoader
from .history_snapshot import hydrate_strategy_snapshots, write_strategy_snapshots
from .history_warmup_polling import HistoryWarmupPoller, WarmupRequest
from .strategy import Strategy

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class NodeWarmupPlan:
    node_id: str
    interval: int
    window: WarmupWindow
    provider: Any | None
    stop_on_ready: bool
    strict: bool
    timeout: float = 60.0

    @classmethod
    def build(
        cls,
        node: Any,
        start: int | None,
        end: int | None,
        *,
        stop_on_ready: bool,
        strict: bool,
        timeout: float = 60.0,
    ) -> NodeWarmupPlan | None:
        interval = getattr(node, "interval", None)
        if interval is None or start is None or end is None:
            return None
        node_id = getattr(node, "node_id", "<unknown>")
        provider = getattr(node, "history_provider", None)
        return cls(
            node_id=node_id,
            interval=interval,
            window=WarmupWindow(start=start, end=end, interval=interval),
            provider=provider,
            stop_on_ready=stop_on_ready,
            strict=strict,
            timeout=timeout,
        )


class HistoryWarmupService:
    """Coordinate history hydration, replay and strict validation."""

    def __init__(self, loader: type[HistoryLoader] = HistoryLoader) -> None:
        self._history_loader = loader

    # ------------------------------------------------------------------
    # Snapshot helpers
    # ------------------------------------------------------------------
    @staticmethod
    def hydrate_snapshots(strategy: Strategy) -> int:
        return hydrate_strategy_snapshots(strategy)

    @staticmethod
    def write_snapshots(strategy: Strategy) -> int:
        return write_strategy_snapshots(strategy)

    # ------------------------------------------------------------------
    async def load_history(
        self, strategy: Strategy, start: int | None, end: int | None
    ) -> None:
        await self._history_loader.load(strategy, start, end)

    # ------------------------------------------------------------------
    @staticmethod
    def missing_ranges(
        coverage: Any,
        start: int,
        end: int,
        interval: int,
    ) -> list[tuple[int, int]]:
        window = WarmupWindow(start=start, end=end, interval=interval)
        gaps = compute_missing_ranges(coverage, window)
        return [(gap.start, gap.end) for gap in gaps]

    async def _ensure_node_with_plan(self, node: Any, plan: NodeWarmupPlan) -> None:
        if plan.provider is None:
            await node.load_history(plan.window.start, plan.window.end)
            return

        poller = HistoryWarmupPoller(plan.provider)
        result = await poller.poll(
            WarmupRequest(
                node_id=plan.node_id,
                interval=plan.interval,
                window=plan.window,
                stop_on_ready=plan.stop_on_ready,
                timeout=plan.timeout,
            ),
            is_ready=lambda: not getattr(node, "pre_warmup", False),
        )

        if result.timed_out:
            logger.warning(
                "history warm-up timed out for %s; proceeding with available data",
                plan.node_id,
            )

        coverage = result.coverage
        if getattr(node, "pre_warmup", False):
            if not coverage:
                coverage = list(
                    await plan.provider.coverage(
                        node_id=plan.node_id, interval=plan.interval
                    )
                )
            bounds = coverage_bounds(coverage)
            if bounds:
                await node.load_history(bounds.start, bounds.end)
            else:
                await node.load_history(plan.window.start, plan.window.end)
        else:
            await node.load_history(plan.window.start, plan.window.end)
            if not coverage:
                coverage = list(
                    await plan.provider.coverage(
                        node_id=plan.node_id, interval=plan.interval
                    )
                )

        if plan.strict:
            coverage = list(
                await plan.provider.coverage(
                    node_id=plan.node_id, interval=plan.interval
                )
            )
            gaps = compute_missing_ranges(coverage, plan.window)
            if gaps or getattr(node, "pre_warmup", False):
                raise RuntimeError(
                    f"history gap for {plan.node_id} in strict mode"
                )

    async def ensure_node_history(
        self,
        node,
        start: int,
        end: int,
        *,
        stop_on_ready: bool = False,
        strict: bool = False,
    ) -> None:
        plan = NodeWarmupPlan.build(
            node,
            start,
            end,
            stop_on_ready=stop_on_ready,
            strict=strict,
        )
        if plan is None:
            return
        await self._ensure_node_with_plan(node, plan)

    async def ensure_history(
        self,
        strategy: Strategy,
        start: int | None = None,
        end: int | None = None,
        *,
        stop_on_ready: bool = False,
        strict: bool = False,
    ) -> None:
        from .node import StreamInput
        from . import runtime as _runtime

        tasks = []
        now = (
            _runtime.FIXED_NOW
            if _runtime.FIXED_NOW is not None
            else int(time.time())
        )
        for node in strategy.nodes:
            if not isinstance(node, StreamInput):
                continue
            if start is None or end is None:
                if node.interval is None or node.period is None:
                    continue
                rng_end = now - (now % node.interval)
                rng_start = rng_end - node.interval * node.period + node.interval
            else:
                rng_start = start
                rng_end = end
            plan = NodeWarmupPlan.build(
                node,
                rng_start,
                rng_end,
                stop_on_ready=stop_on_ready,
                strict=strict,
            )
            if plan is None:
                continue
            tasks.append(
                asyncio.create_task(self._ensure_node_with_plan(node, plan))
            )
        if tasks:
            await asyncio.gather(*tasks)

    # ------------------------------------------------------------------
    def collect_history_events(
        self, strategy: Strategy, start: int | None, end: int | None
    ) -> list[tuple[int, Any, Any]]:
        from .node import StreamInput

        events: list[tuple[int, Any, Any]] = []
        for node in strategy.nodes:
            if not isinstance(node, StreamInput):
                continue
            snapshot = node.cache._snapshot().get(node.node_id, {})
            items = snapshot.get(node.interval, []) if node.interval is not None else []
            for ts, payload in items:
                if start is not None and ts < start:
                    continue
                if end is not None and ts > end:
                    continue
                events.append((ts, node, payload))
        events.sort(key=lambda event: event[0])
        return events

    def replay_history_events(
        self,
        strategy: Strategy,
        events: list[tuple[int, Any, Any]],
        *,
        on_missing: str = "skip",
    ) -> None:
        for ts, src, payload in events:
            for node in strategy.nodes:
                if src in getattr(node, "inputs", []):
                    from .runner import Runner

                    Runner.feed_queue_data(
                        node,
                        src.node_id,
                        src.interval,
                        ts,
                        payload,
                        on_missing=on_missing,
                    )

    async def replay_history(
        self,
        strategy: Strategy,
        start: int | None,
        end: int | None,
        *,
        on_missing: str = "skip",
    ) -> None:
        from .node import StreamInput
        from qmtl import Pipeline

        pipeline = Pipeline(strategy.nodes)

        async def collect(node: StreamInput) -> list[tuple[int, StreamInput, Any]]:
            items = node.cache.get_slice(node.node_id, node.interval, count=node.period)
            return [
                (ts, node, payload)
                for ts, payload in items
                if (start is None or ts >= start) and (end is None or ts <= end)
            ]

        tasks = [
            asyncio.create_task(collect(node))
            for node in strategy.nodes
            if isinstance(node, StreamInput) and node.interval is not None
        ]

        events: list[tuple[int, StreamInput, Any]] = []
        if tasks:
            results = await asyncio.gather(*tasks)
            for result in results:
                events.extend(result)
        events.sort(key=lambda event: event[0])

        for ts, node, payload in events:
            pipeline.feed(node, ts, payload, on_missing=on_missing)

    def replay_events_simple(self, strategy: Strategy) -> None:
        from .cache_view import CacheView
        from .node import StreamInput

        events = self.collect_history_events(strategy, None, None)
        by_ts: dict[int, list[tuple[StreamInput, Any]]] = {}
        for ts, node, payload in events:
            by_ts.setdefault(ts, []).append((node, payload))

        for ts in sorted(by_ts):
            seeds = by_ts[ts]
            event_values: dict[str, dict[int, list[tuple[int, Any]]]] = {}
            for src, payload in seeds:
                event_values.setdefault(src.node_id, {}).setdefault(src.interval, []).append(
                    (ts, payload)
                )

            progressed = True
            done: set[str] = set()
            while progressed:
                progressed = False
                for node in strategy.nodes:
                    if not getattr(node, "compute_fn", None):
                        continue
                    if not getattr(node, "execute", True):
                        continue
                    inputs = getattr(node, "inputs", [])
                    if not inputs:
                        continue
                    node_id = getattr(node, "node_id", None)
                    if node_id is None or node_id in done:
                        continue
                    ready = True
                    iterable = inputs if isinstance(inputs, list) else [inputs]
                    for upstream in iterable:
                        if upstream is None:
                            continue
                        uid = getattr(upstream, "node_id", None)
                        interval = getattr(upstream, "interval", None)
                        if uid is None or interval is None:
                            continue
                        if uid not in event_values or interval not in event_values[uid]:
                            ready = False
                            break
                    if not ready:
                        continue
                    view = CacheView(event_values)
                    result = node.compute_fn(view)
                    from .runner import Runner

                    Runner._postprocess_result(node, result)
                    n_uid = getattr(node, "node_id", None)
                    interval = getattr(node, "interval", None)
                    if n_uid is not None and interval is not None:
                        event_values.setdefault(n_uid, {}).setdefault(interval, []).append(
                            (ts, result)
                        )
                        done.add(n_uid)
                        progressed = True

    # ------------------------------------------------------------------
    async def warmup_strategy(
        self,
        strategy: Strategy,
        *,
        offline_mode: bool,
        history_start: Any | None,
        history_end: Any | None,
    ) -> None:
        from .node import StreamInput
        from . import runtime as _runtime

        self.hydrate_snapshots(strategy)

        has_provider = any(
            isinstance(node, StreamInput)
            and getattr(node, "history_provider", None) is not None
            for node in strategy.nodes
        )

        strict_mode = bool(_runtime.FAIL_ON_HISTORY_GAP)

        h_start = history_start
        h_end = history_end
        if offline_mode and h_start is None and h_end is None and not has_provider:
            h_start, h_end = 1, 2

        ensure_history = has_provider or (h_start is not None and h_end is not None)
        if not ensure_history and offline_mode:
            has_cached = False
            for node in strategy.nodes:
                if isinstance(node, StreamInput):
                    try:
                        snapshot = node.cache._snapshot()[node.node_id].get(node.interval, [])
                        if snapshot:
                            has_cached = True
                            break
                    except KeyError:
                        continue
            if not has_cached:
                h_start, h_end = 1, 2
                ensure_history = True

        if ensure_history:
            await self.ensure_history(
                strategy,
                h_start if isinstance(h_start, int) else None,
                h_end if isinstance(h_end, int) else None,
                stop_on_ready=True,
                strict=strict_mode,
            )

        if offline_mode:
            if has_provider:
                await self.replay_history(strategy, None, None)
            if strict_mode:
                await self._enforce_strict_mode(strategy)

    async def _enforce_strict_mode(self, strategy: Strategy) -> None:
        from .node import StreamInput

        for node in strategy.nodes:
            if isinstance(node, StreamInput) and getattr(node, "pre_warmup", False):
                raise RuntimeError("history pre-warmup unresolved in strict mode")

        for node in strategy.nodes:
            if not isinstance(node, StreamInput):
                continue
            provider = getattr(node, "history_provider", None)
            if provider is None:
                continue
            try:
                snapshot = node.cache._snapshot()[node.node_id].get(node.interval, [])
                ts_sorted = sorted(ts for ts, _ in snapshot)
            except KeyError as exc:
                raise RuntimeError("history missing in strict mode") from exc
            coverage = await provider.coverage(node_id=node.node_id, interval=node.interval)
            ensure_strict_history(
                ts_sorted,
                getattr(node, "interval", None),
                getattr(node, "period", 1) or 1,
                coverage,
            )


__all__ = ["HistoryWarmupService"]
