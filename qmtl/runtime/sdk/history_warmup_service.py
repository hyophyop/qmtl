from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Iterable

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


@dataclass(frozen=True)
class StrategyWarmupPlan:
    ensure_history: bool
    start: int | None
    end: int | None
    strict_mode: bool
    needs_replay: bool
    enforce_strict: bool


class HistoryWarmupService:
    """Coordinate history hydration, replay and strict validation."""

    def __init__(self, loader: type[HistoryLoader] = HistoryLoader) -> None:
        self._history_loader = loader

    # ------------------------------------------------------------------
    # Node helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _stream_inputs(strategy: Strategy) -> Iterable[Any]:
        from .node import StreamInput

        return (
            node for node in getattr(strategy, "nodes", []) if isinstance(node, StreamInput)
        )

    @staticmethod
    def _node_cache_rows(node: Any) -> dict[int, list[tuple[int, Any]]]:
        snapshot_method = getattr(getattr(node, "cache", None), "_snapshot", None)
        if not callable(snapshot_method):
            return {}
        snapshot = snapshot_method()
        node_rows = snapshot.get(getattr(node, "node_id", ""), {})
        if isinstance(node_rows, dict):
            return node_rows
        return {}

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
            await self._load_node_history_range(node, plan.window.start, plan.window.end)
            return

        result = await self._poll_history_provider(node, plan)
        coverage = await self._resolve_provider_coverage(plan, result.coverage)

        if getattr(node, "pre_warmup", False):
            await self._load_pre_warmup_node(node, plan, coverage)
        else:
            await self._load_node_history_range(node, plan.window.start, plan.window.end)
            if not coverage and not plan.stop_on_ready:
                await self._fetch_provider_coverage(plan)

        if plan.strict:
            await self._validate_strict_node(node, plan)

    async def _poll_history_provider(
        self, node: Any, plan: NodeWarmupPlan
    ) -> Any:
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
        return result

    async def _resolve_provider_coverage(
        self, plan: NodeWarmupPlan, coverage: Any
    ) -> list[Any]:
        if coverage:
            return list(coverage)
        if plan.stop_on_ready or plan.provider is None:
            return []
        return await self._fetch_provider_coverage(plan)

    async def _load_pre_warmup_node(
        self, node: Any, plan: NodeWarmupPlan, coverage: list[Any]
    ) -> None:
        effective = coverage
        if not effective and not plan.stop_on_ready:
            effective = await self._fetch_provider_coverage(plan)
        bounds = coverage_bounds(effective)
        if bounds:
            await self._load_node_history_range(node, bounds.start, bounds.end)
            return
        cached_bounds = self._cached_history_bounds(node, plan)
        if cached_bounds is not None:
            await self._load_node_history_range(node, *cached_bounds)
            return
        await self._load_node_history_range(node, plan.window.start, plan.window.end)

    async def _fetch_provider_coverage(self, plan: NodeWarmupPlan) -> list[Any]:
        if plan.provider is None:
            return []
        coverage = await plan.provider.coverage(
            node_id=plan.node_id, interval=plan.interval
        )
        return list(coverage)

    @staticmethod
    async def _load_node_history_range(node: Any, start: int, end: int) -> None:
        await node.load_history(start, end)

    def _cached_history_bounds(
        self, node: Any, plan: NodeWarmupPlan
    ) -> tuple[int, int] | None:
        rows = self._node_cache_rows(node).get(plan.interval, [])
        if not rows:
            return None
        timestamps = [ts for ts, _ in rows]
        if not timestamps:
            return None
        return min(timestamps), max(timestamps)

    async def _validate_strict_node(self, node: Any, plan: NodeWarmupPlan) -> None:
        coverage = await self._fetch_provider_coverage(plan)
        gaps = compute_missing_ranges(coverage, plan.window)
        if gaps or getattr(node, "pre_warmup", False):
            raise RuntimeError(f"history gap for {plan.node_id} in strict mode")

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
        plans = list(
            self._iter_node_plans(
                strategy,
                start,
                end,
                stop_on_ready=stop_on_ready,
                strict=strict,
            )
        )
        if not plans:
            return
        await asyncio.gather(
            *[
                asyncio.create_task(self._ensure_node_with_plan(node, plan))
                for node, plan in plans
            ]
        )

    # ------------------------------------------------------------------
    def collect_history_events(
        self, strategy: Strategy, start: int | None, end: int | None
    ) -> list[tuple[int, Any, Any]]:
        events: list[tuple[int, Any, Any]] = []
        for node in self._stream_inputs(strategy):
            if node.interval is None:
                continue
            items = self._node_cache_rows(node).get(node.interval, [])
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
        from qmtl.runtime.pipeline import Pipeline

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
        events = self.collect_history_events(strategy, None, None)
        grouped = self._group_events_by_timestamp(events)
        for ts in sorted(grouped):
            self._replay_timestamp(strategy, ts, grouped[ts])

    # ------------------------------------------------------------------
    @staticmethod
    def _group_events_by_timestamp(
        events: list[tuple[int, Any, Any]]
    ) -> dict[int, list[tuple[Any, Any]]]:
        grouped: dict[int, list[tuple[Any, Any]]] = defaultdict(list)
        for ts, node, payload in events:
            grouped[ts].append((node, payload))
        return grouped

    @staticmethod
    def _initialize_event_values(
        ts: int, seeds: list[tuple[Any, Any]]
    ) -> dict[str, dict[int, list[tuple[int, Any]]]]:
        event_values: dict[str, dict[int, list[tuple[int, Any]]]] = {}
        for src, payload in seeds:
            node_id = getattr(src, "node_id", None)
            interval = getattr(src, "interval", None)
            if node_id is None or interval is None:
                continue
            event_values.setdefault(node_id, {}).setdefault(interval, []).append((ts, payload))
        return event_values

    @staticmethod
    def _should_process_node(node: Any, done: set[str]) -> bool:
        if not getattr(node, "compute_fn", None):
            return False
        if not getattr(node, "execute", True):
            return False
        inputs = getattr(node, "inputs", [])
        if not inputs:
            return False
        node_id = getattr(node, "node_id", None)
        return node_id is not None and node_id not in done

    @staticmethod
    def _node_inputs_ready(node: Any, event_values: dict[str, dict[int, list[tuple[int, Any]]]]) -> bool:
        inputs = getattr(node, "inputs", [])
        iterable = inputs if isinstance(inputs, list) else [inputs]
        for upstream in iterable:
            if upstream is None:
                continue
            uid = getattr(upstream, "node_id", None)
            interval = getattr(upstream, "interval", None)
            if uid is None or interval is None:
                continue
            if uid not in event_values or interval not in event_values[uid]:
                return False
        return True

    @staticmethod
    def _execute_node(node: Any, event_values: dict[str, dict[int, list[tuple[int, Any]]]]) -> Any:
        from .cache_view import CacheView
        from .runner import Runner

        view = CacheView(event_values)
        result = node.compute_fn(view)
        Runner._postprocess_result(node, result)
        return result

    @staticmethod
    def _record_node_result(
        node: Any,
        ts: int,
        result: Any,
        event_values: dict[str, dict[int, list[tuple[int, Any]]]],
        done: set[str],
    ) -> None:
        node_id = getattr(node, "node_id", None)
        interval = getattr(node, "interval", None)
        if node_id is None or interval is None:
            return
        event_values.setdefault(node_id, {}).setdefault(interval, []).append((ts, result))
        done.add(node_id)

    def _replay_timestamp(
        self,
        strategy: Strategy,
        ts: int,
        seeds: list[tuple[Any, Any]],
    ) -> None:
        event_values = self._initialize_event_values(ts, seeds)
        done: set[str] = set()
        progressed = True
        while progressed:
            progressed = False
            for node in getattr(strategy, "nodes", []):
                if not self._should_process_node(node, done):
                    continue
                if not self._node_inputs_ready(node, event_values):
                    continue
                result = self._execute_node(node, event_values)
                self._record_node_result(node, ts, result, event_values, done)
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
        self.hydrate_snapshots(strategy)
        plan = self._plan_strategy_warmup(
            strategy,
            offline_mode=offline_mode,
            history_start=history_start,
            history_end=history_end,
        )

        if plan.ensure_history:
            await self.ensure_history(
                strategy,
                plan.start,
                plan.end,
                stop_on_ready=True,
                strict=plan.strict_mode,
            )

        if plan.needs_replay:
            await self.replay_history(strategy, None, None)

        if plan.enforce_strict:
            await self._enforce_strict_mode(strategy)

    async def _enforce_strict_mode(self, strategy: Strategy) -> None:
        for node in self._stream_inputs(strategy):
            if getattr(node, "pre_warmup", False):
                raise RuntimeError("history pre-warmup unresolved in strict mode")

        for node in self._stream_inputs(strategy):
            provider = getattr(node, "history_provider", None)
            if provider is None:
                continue
            try:
                snapshot = self._node_cache_rows(node).get(node.interval, [])
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

    # ------------------------------------------------------------------
    def _iter_node_plans(
        self,
        strategy: Strategy,
        start: int | None,
        end: int | None,
        *,
        stop_on_ready: bool,
        strict: bool,
    ) -> list[tuple[Any, NodeWarmupPlan]]:
        now = self._resolve_now()
        plans: list[tuple[Any, NodeWarmupPlan]] = []
        for node in self._stream_inputs(strategy):
            window = self._resolve_node_window(node, start, end, now)
            if window is None:
                continue
            rng_start, rng_end = window
            plan = NodeWarmupPlan.build(
                node,
                rng_start,
                rng_end,
                stop_on_ready=stop_on_ready,
                strict=strict,
            )
            if plan is not None:
                plans.append((node, plan))
        return plans

    @staticmethod
    def _resolve_now() -> int:
        from . import runtime as _runtime

        if _runtime.FIXED_NOW is not None:
            return _runtime.FIXED_NOW
        return int(time.time())

    @staticmethod
    def _resolve_node_window(
        node: Any,
        start: int | None,
        end: int | None,
        now: int,
    ) -> tuple[int, int] | None:
        if start is not None and end is not None:
            return start, end
        interval = getattr(node, "interval", None)
        period = getattr(node, "period", None)
        if interval is None or period is None:
            return None
        rng_end = now - (now % interval)
        rng_start = rng_end - interval * period + interval
        return rng_start, rng_end

    def _plan_strategy_warmup(
        self,
        strategy: Strategy,
        *,
        offline_mode: bool,
        history_start: Any | None,
        history_end: Any | None,
    ) -> StrategyWarmupPlan:
        from . import runtime as _runtime

        has_provider = any(
            getattr(node, "history_provider", None) is not None
            for node in self._stream_inputs(strategy)
        )

        strict_mode = bool(_runtime.FAIL_ON_HISTORY_GAP)

        start = history_start if isinstance(history_start, int) else None
        end = history_end if isinstance(history_end, int) else None

        if offline_mode and start is None and end is None and not has_provider:
            start, end = 1, 2

        ensure_history = has_provider or (start is not None and end is not None)
        if offline_mode and not ensure_history and not self._has_cached_history(strategy):
            start, end = 1, 2
            ensure_history = True

        return StrategyWarmupPlan(
            ensure_history=ensure_history,
            start=start,
            end=end,
            strict_mode=strict_mode,
            needs_replay=offline_mode and has_provider,
            enforce_strict=offline_mode and strict_mode,
        )

    @staticmethod
    def _has_cached_history(strategy: Strategy) -> bool:
        for node in HistoryWarmupService._stream_inputs(strategy):
            if node.interval is None:
                continue
            if HistoryWarmupService._node_cache_rows(node).get(node.interval):
                return True
        return False


__all__ = ["HistoryWarmupService"]
