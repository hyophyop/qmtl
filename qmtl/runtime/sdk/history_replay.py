from __future__ import annotations

import asyncio
import importlib
from collections import defaultdict
from typing import Any, Callable, Iterable, TYPE_CHECKING

from .node import StreamInput

if TYPE_CHECKING:
    from .strategy import Strategy


def _get_runner():
    try:
        module = importlib.import_module("qmtl.runtime.sdk.runner")
        return module.Runner
    except Exception:
        return None


class HistoryReplayer:
    def __init__(
        self,
        stream_inputs: Callable[[Strategy], Iterable[Any]],
        node_cache_rows: Callable[[Any], dict[int, list[tuple[int, Any]]]],
        runner_factory: Callable[[], Any] | None = None,
    ) -> None:
        self._stream_inputs = stream_inputs
        self._node_cache_rows = node_cache_rows
        self._runner_factory = runner_factory or _get_runner

    def collect_events(
        self, strategy: Strategy, start: int | None, end: int | None
    ) -> list[tuple[int, Any, Any]]:
        events: list[tuple[int, Any, Any]] = []
        for node in self._stream_inputs(strategy):
            interval = getattr(node, "interval", None)
            if interval is None:
                continue
            items = self._node_cache_rows(node).get(interval, [])
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
        runner = self._runner_factory()
        for ts, src, payload in events:
            for node in getattr(strategy, "nodes", []):
                if src in getattr(node, "inputs", []):
                    feed = runner.feed_queue_data if runner else lambda *args, **kwargs: None
                    feed(
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
        pipeline_mod = importlib.import_module("qmtl.runtime.pipeline")
        Pipeline = getattr(pipeline_mod, "Pipeline")

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
        events = self.collect_events(strategy, None, None)
        runner = self._runner_factory()
        grouped = self._group_events_by_timestamp(events)
        for ts in sorted(grouped):
            self._replay_timestamp(strategy, ts, grouped[ts], runner)

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

    def _execute_node(
        self,
        node: Any,
        event_values: dict[str, dict[int, list[tuple[int, Any]]]],
        runner: Any,
    ) -> Any:
        from .cache_view import CacheView

        view: CacheView[Any] = CacheView(event_values)
        result = node.compute_fn(view)
        if runner is not None:
            runner._postprocess_result(node, result)
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
        runner: Any,
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
                result = self._execute_node(node, event_values, runner)
                self._record_node_result(node, ts, result, event_values, done)
                progressed = True

