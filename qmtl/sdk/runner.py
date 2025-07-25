from __future__ import annotations

import base64
import json
import asyncio
import time
import os
from typing import Optional, Iterable
import logging
import httpx

logger = logging.getLogger(__name__)

from .strategy import Strategy
from .tagquery_manager import TagQueryManager
from qmtl.common import AsyncCircuitBreaker

try:  # Optional aiokafka dependency
    from aiokafka import AIOKafkaConsumer  # type: ignore
except Exception:  # pragma: no cover - aiokafka not installed
    AIOKafkaConsumer = None  # type: ignore
try:  # Optional Ray dependency
    import ray  # type: ignore
except Exception:  # pragma: no cover - Ray not installed
    ray = None  # type: ignore


class Runner:
    """Execute strategies in various modes."""

    _ray_available = False
    _kafka_available = AIOKafkaConsumer is not None
    _gateway_cb: AsyncCircuitBreaker | None = None

    @classmethod
    def enable_ray(cls, enable: bool = True) -> None:
        """Toggle Ray-based execution explicitly."""
        if enable and ray is None:
            raise RuntimeError("Ray not installed")
        cls._ray_available = enable

    @classmethod
    def disable_ray(cls) -> None:
        cls.enable_ray(False)

    # ------------------------------------------------------------------

    @classmethod
    def set_gateway_circuit_breaker(
        cls, cb: AsyncCircuitBreaker | None
    ) -> None:
        """Configure circuit breaker for Gateway communication."""
        cls._gateway_cb = cb

    @classmethod
    def _get_gateway_circuit_breaker(cls) -> AsyncCircuitBreaker | None:
        if cls._gateway_cb is None:
            max_failures = os.getenv("QMTL_GW_CB_MAX_FAILURES")
            reset_timeout = os.getenv("QMTL_GW_CB_RESET_TIMEOUT")
            if max_failures or reset_timeout:
                cls._gateway_cb = AsyncCircuitBreaker(
                    max_failures=int(max_failures or 3),
                    reset_timeout=float(reset_timeout or 60.0),
                )
        return cls._gateway_cb

    # ------------------------------------------------------------------

    @staticmethod
    def _execute_compute_fn(fn, cache_view) -> None:
        """Run ``fn`` using Ray when available."""
        if Runner._ray_available and ray is not None:
            if not ray.is_initialized():  # type: ignore[attr-defined]
                ray.init(ignore_reinit_error=True)  # type: ignore[attr-defined]
            ray.remote(fn).remote(cache_view)  # type: ignore[attr-defined]
        else:
            fn(cache_view)

    @staticmethod
    async def _post_gateway_async(
        *,
        gateway_url: str,
        dag: dict,
        meta: Optional[dict],
        run_type: str,
        circuit_breaker: AsyncCircuitBreaker | None = None,
    ) -> dict:
        url = gateway_url.rstrip("/") + "/strategies"
        from qmtl.common import crc32_of_list

        payload = {
            "dag_json": base64.b64encode(json.dumps(dag).encode()).decode(),
            "meta": meta,
            "run_type": run_type,
            "node_ids_crc32": crc32_of_list(n["node_id"] for n in dag.get("nodes", [])),
        }
        if circuit_breaker is None:
            circuit_breaker = Runner._get_gateway_circuit_breaker()
        async with httpx.AsyncClient() as client:
            post_fn = client.post
            if circuit_breaker is not None:
                post_fn = circuit_breaker(post_fn)
            resp = await post_fn(url, json=payload)
        if resp.status_code == 202:
            return resp.json().get("queue_map", {})
        if resp.status_code == 409:
            raise RuntimeError("duplicate strategy")
        if resp.status_code == 422:
            raise RuntimeError("invalid strategy payload")
        resp.raise_for_status()
        return {}

    @staticmethod
    def _prepare(strategy_cls: type[Strategy]) -> Strategy:
        strategy = strategy_cls()
        strategy.setup()
        return strategy

    @staticmethod
    def _apply_queue_map(strategy: Strategy, queue_map: dict[str, str | list[str]]) -> None:
        from .node import TagQueryNode

        for node in strategy.nodes:
            mapping = queue_map.get(node.node_id)
            old_execute = node.execute
            if isinstance(node, TagQueryNode):
                if isinstance(mapping, list):
                    node.upstreams = list(mapping)
                    node.execute = bool(mapping)
                else:
                    node.upstreams = []
                    node.execute = False
            else:
                if mapping:
                    node.execute = False
                    node.queue_topic = mapping  # type: ignore[assignment]
                else:
                    node.execute = True
                    node.queue_topic = None

            if node.execute != old_execute:
                logger.debug(
                    "execute changed for %s: %s -> %s (mapping=%s)",
                    node.node_id,
                    old_execute,
                    node.execute,
                    mapping,
                )

    @staticmethod
    def _init_tag_manager(strategy: Strategy, gateway_url: str | None) -> TagQueryManager:
        from .node import TagQueryNode

        manager = TagQueryManager(gateway_url)
        for n in strategy.nodes:
            if isinstance(n, TagQueryNode):
                manager.register(n)
        setattr(strategy, "tag_query_manager", manager)
        return manager

    @staticmethod
    async def _load_history(
        strategy: Strategy, start: int | None = None, end: int | None = None
    ) -> None:
        """Load history for all StreamInput nodes."""
        from .node import StreamInput

        if start is None or end is None:
            return

        tasks = [
            asyncio.create_task(n.load_history(start, end))
            for n in strategy.nodes
            if isinstance(n, StreamInput)
        ]
        if tasks:
            await asyncio.gather(*tasks)

    # ------------------------------------------------------------------
    @staticmethod
    def _missing_ranges(
        coverage: Iterable[tuple[int, int]], start: int, end: int, interval: int
    ) -> list[tuple[int, int]]:
        """Return timestamp gaps in ``[start, end]``."""
        ranges = sorted([tuple(r) for r in coverage])
        merged: list[tuple[int, int]] = []
        for s, e in ranges:
            if not merged:
                merged.append((s, e))
                continue
            ls, le = merged[-1]
            if s <= le + interval:
                merged[-1] = (ls, max(le, e))
            else:
                merged.append((s, e))

        gaps: list[tuple[int, int]] = []
        cur = start
        for s, e in merged:
            if e < start:
                continue
            if s > end:
                break
            if s > cur:
                gaps.append((cur, min(s - interval, end)))
            cur = max(cur, e + interval)
            if cur > end:
                break
        if cur <= end:
            gaps.append((cur, end))
        return [g for g in gaps if g[0] <= g[1]]

    @staticmethod
    async def _ensure_node_history(
        node,
        start: int,
        end: int,
        *,
        stop_on_ready: bool = False,
    ) -> None:
        """Ensure history coverage for a single ``StreamInput`` node."""
        if node.interval is None or start is None or end is None:
            return
        provider = getattr(node, "history_provider", None)
        if provider is None:
            await node.load_history(start, end)
            return

        while node.pre_warmup:
            cov = await provider.coverage(
                node_id=node.node_id, interval=node.interval
            )
            missing = Runner._missing_ranges(cov, start, end, node.interval)
            if not missing:
                await node.load_history(start, end)
                return
            for s, e in missing:
                await provider.fill_missing(
                    s, e, node_id=node.node_id, interval=node.interval
                )
                if stop_on_ready and not node.pre_warmup:
                    return

    @staticmethod
    async def _ensure_history(
        strategy: Strategy,
        start: int | None = None,
        end: int | None = None,
        *,
        stop_on_ready: bool = False,
    ) -> None:
        """Ensure history coverage for all ``StreamInput`` nodes."""
        from .node import StreamInput

        tasks = []
        now = int(time.time())
        for n in strategy.nodes:
            if not isinstance(n, StreamInput):
                continue
            if start is None or end is None:
                if n.interval is None or n.period is None:
                    continue
                rng_end = now - (now % n.interval)
                rng_start = rng_end - n.interval * n.period + n.interval
            else:
                rng_start = start
                rng_end = end
            task = asyncio.create_task(
                Runner._ensure_node_history(
                    n, rng_start, rng_end, stop_on_ready=stop_on_ready
                )
            )
            tasks.append(task)
        if tasks:
            await asyncio.gather(*tasks)

    # ------------------------------------------------------------------
    @staticmethod
    def feed_queue_data(
        node,
        queue_id: str,
        interval: int,
        timestamp: int,
        payload,
        *,
        on_missing: str = "skip",
    ):
        """Insert queue data into ``node`` and trigger its ``compute_fn``.

        Returns the compute function result when executed locally. ``None`` is
        returned if the node did not run or Ray was used for execution.
        """
        ready = node.feed(
            queue_id,
            interval,
            timestamp,
            payload,
            on_missing=on_missing,
        )

        result = None
        if ready and node.execute and node.compute_fn:
            if Runner._ray_available and ray is not None:
                Runner._execute_compute_fn(node.compute_fn, node.cache.view())
            else:
                result = node.compute_fn(node.cache.view())
        return result

    # ------------------------------------------------------------------
    @staticmethod
    async def _consume_node(
        node,
        *,
        bootstrap_servers: str,
        stop_event: asyncio.Event,
    ) -> None:
        """Consume Kafka messages for ``node`` and feed them into the cache."""
        if not Runner._kafka_available:
            raise RuntimeError("aiokafka not available")
        consumer = AIOKafkaConsumer(
            node.queue_topic,
            bootstrap_servers=bootstrap_servers,
            enable_auto_commit=True,
        )
        await consumer.start()
        try:
            async for msg in consumer:
                try:
                    payload = json.loads(msg.value)
                except Exception:
                    payload = msg.value
                ts = int(msg.timestamp / 1000)
                Runner.feed_queue_data(
                    node,
                    node.queue_topic,
                    node.interval,
                    ts,
                    payload,
                )
                if stop_event.is_set():
                    break
        finally:
            await consumer.stop()

    @staticmethod
    def spawn_consumer_tasks(
        strategy: Strategy,
        *,
        bootstrap_servers: str,
        stop_event: asyncio.Event,
    ) -> list[asyncio.Task]:
        """Spawn Kafka consumer tasks for nodes with ``queue_topic``."""
        tasks = []
        for n in strategy.nodes:
            if n.queue_topic:
                tasks.append(
                    asyncio.create_task(
                        Runner._consume_node(
                            n,
                            bootstrap_servers=bootstrap_servers,
                            stop_event=stop_event,
                        )
                    )
                )
        return tasks

    # ------------------------------------------------------------------
    @staticmethod
    def _collect_history_events(
        strategy: Strategy, start: int | None, end: int | None
    ) -> list[tuple[int, any, any]]:
        """Gather cached history items for all ``StreamInput`` nodes."""
        from .node import StreamInput

        events: list[tuple[int, any, any]] = []
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
        events.sort(key=lambda e: e[0])
        return events

    @staticmethod
    def run_pipeline(strategy: Strategy) -> None:
        """Execute a :class:`Pipeline` using cached history from ``strategy``."""
        from qmtl import Pipeline

        pipeline = Pipeline(strategy.nodes)
        events = Runner._collect_history_events(strategy, None, None)
        for ts, node, payload in events:
            pipeline.feed(node, ts, payload)

    @staticmethod
    def _maybe_int(value) -> int | None:
        try:
            return int(value)
        except Exception:
            return None

    @staticmethod
    async def _replay_history(
        strategy: Strategy,
        start: int | None,
        end: int | None,
        *,
        on_missing: str = "skip",
    ) -> None:
        """Replay cached history through a :class:`Pipeline`."""
        from .node import StreamInput
        from qmtl import Pipeline

        pipeline = Pipeline(strategy.nodes)

        async def collect(node: StreamInput) -> list[tuple[int, StreamInput, any]]:
            items = node.cache.get_slice(node.node_id, node.interval, count=node.period)
            return [
                (ts, node, payload)
                for ts, payload in items
                if (start is None or ts >= start) and (end is None or ts <= end)
            ]

        tasks = [
            asyncio.create_task(collect(n))
            for n in strategy.nodes
            if isinstance(n, StreamInput) and n.interval is not None
        ]

        events: list[tuple[int, StreamInput, any]] = []
        if tasks:
            results = await asyncio.gather(*tasks)
            for res in results:
                events.extend(res)

        events.sort(key=lambda e: e[0])

        for ts, node, payload in events:
            pipeline.feed(node, ts, payload, on_missing=on_missing)

    @staticmethod
    def _replay_history_events(
        strategy: Strategy,
        events: list[tuple[int, any, any]],
        *,
        on_missing: str = "skip",
    ) -> None:
        """Feed cached history to dependent nodes in timestamp order."""
        for ts, src, payload in events:
            for node in strategy.nodes:
                if src in node.inputs:
                    Runner.feed_queue_data(
                        node,
                        src.node_id,
                        src.interval,
                        ts,
                        payload,
                        on_missing=on_missing,
                    )

    @staticmethod
    async def backtest_async(
        strategy_cls: type[Strategy],
        *,
        start_time=None,
        end_time=None,
        on_missing="skip",
        gateway_url: str | None = None,
        meta: Optional[dict] = None,
    ) -> Strategy:
        """Run strategy in backtest mode. Requires ``gateway_url``."""
        if start_time is None or end_time is None:
            raise ValueError("start_time and end_time are required")
        strategy = Runner._prepare(strategy_cls)
        manager = Runner._init_tag_manager(strategy, gateway_url)
        logger.info(
            f"[BACKTEST] {strategy_cls.__name__} from {start_time} to {end_time} on_missing={on_missing}"
        )
        dag = strategy.serialize()
        logger.info("Sending DAG to service: %s", [n["node_id"] for n in dag["nodes"]])
        if not gateway_url:
            raise RuntimeError("gateway_url is required for backtest mode")

        try:
            queue_map = await Runner._post_gateway_async(
                gateway_url=gateway_url,
                dag=dag,
                meta=meta,
                run_type="backtest",
                circuit_breaker=Runner._get_gateway_circuit_breaker(),
            )
        except httpx.RequestError as exc:
            raise RuntimeError(
                f"게이트웨이({gateway_url})에 접속할 수 없습니다: 서비스 가동 여부 확인 필요"
            ) from exc

        Runner._apply_queue_map(strategy, queue_map)
        await manager.resolve_tags(offline=False)
        await Runner._ensure_history(strategy, start_time, end_time)
        start = Runner._maybe_int(start_time)
        end = Runner._maybe_int(end_time)
        await Runner._replay_history(strategy, start, end, on_missing=on_missing)
        return strategy

    @staticmethod
    def backtest(
        strategy_cls: type[Strategy],
        *,
        start_time=None,
        end_time=None,
        on_missing="skip",
        gateway_url: str | None = None,
        meta: Optional[dict] = None,
    ) -> Strategy:
        return asyncio.run(
            Runner.backtest_async(
                strategy_cls,
                start_time=start_time,
                end_time=end_time,
                on_missing=on_missing,
                gateway_url=gateway_url,
                meta=meta,
            )
        )

    @staticmethod
    async def dryrun_async(
        strategy_cls: type[Strategy],
        *,
        gateway_url: str | None = None,
        meta: Optional[dict] = None,
        offline: bool = False,
    ) -> Strategy:
        """Run strategy in dry-run (paper trading) mode. Requires ``gateway_url``."""
        strategy = Runner._prepare(strategy_cls)
        manager = Runner._init_tag_manager(strategy, gateway_url)
        logger.info(f"[DRYRUN] {strategy_cls.__name__} starting")
        dag = strategy.serialize()
        logger.info("Sending DAG to service: %s", [n["node_id"] for n in dag["nodes"]])

        if not gateway_url:
            raise RuntimeError("gateway_url is required for dry-run mode")

        try:
            queue_map = await Runner._post_gateway_async(
                gateway_url=gateway_url,
                dag=dag,
                meta=meta,
                run_type="dry-run",
                circuit_breaker=Runner._get_gateway_circuit_breaker(),
            )
        except httpx.RequestError as exc:
            raise RuntimeError(
                f"게이트웨이({gateway_url})에 접속할 수 없습니다: 서비스 가동 여부 확인 필요"
            ) from exc

        Runner._apply_queue_map(strategy, queue_map)
        offline_mode = offline or not Runner._kafka_available
        await manager.resolve_tags(offline=offline_mode)
        await Runner._ensure_history(strategy, None, None, stop_on_ready=True)
        if offline_mode:
            Runner.run_pipeline(strategy)
        # Placeholder for dry-run logic when Kafka available
        return strategy

    def dryrun(
        strategy_cls: type[Strategy],
        *,
        gateway_url: str | None = None,
        meta: Optional[dict] = None,
        offline: bool = False,
    ) -> Strategy:
        return asyncio.run(
            Runner.dryrun_async(
                strategy_cls,
                gateway_url=gateway_url,
                meta=meta,
                offline=offline,
            )
        )

    @staticmethod
    async def live_async(
        strategy_cls: type[Strategy],
        *,
        gateway_url: str | None = None,
        meta: Optional[dict] = None,
        offline: bool = False,
    ) -> Strategy:
        """Run strategy in live trading mode. Requires ``gateway_url``."""
        strategy = Runner._prepare(strategy_cls)
        manager = Runner._init_tag_manager(strategy, gateway_url)
        logger.info(f"[LIVE] {strategy_cls.__name__} starting")
        dag = strategy.serialize()
        logger.info("Sending DAG to service: %s", [n["node_id"] for n in dag["nodes"]])

        if not gateway_url:
            raise RuntimeError("gateway_url is required for live mode")

        try:
            queue_map = await Runner._post_gateway_async(
                gateway_url=gateway_url,
                dag=dag,
                meta=meta,
                run_type="live",
                circuit_breaker=Runner._get_gateway_circuit_breaker(),
            )
        except httpx.RequestError as exc:
            raise RuntimeError(
                f"게이트웨이({gateway_url})에 접속할 수 없습니다: 서비스 가동 여부 확인 필요"
            ) from exc

        Runner._apply_queue_map(strategy, queue_map)
        offline_mode = offline or not Runner._kafka_available
        await manager.resolve_tags(offline=offline_mode)
        await Runner._ensure_history(strategy, None, None, stop_on_ready=True)
        if offline_mode:
            Runner.run_pipeline(strategy)
        else:
            await manager.start()

        # Placeholder for live trading logic
        return strategy

    @staticmethod
    def live(
        strategy_cls: type[Strategy],
        *,
        gateway_url: str | None = None,
        meta: Optional[dict] = None,
        offline: bool = False,
    ) -> Strategy:
        return asyncio.run(
            Runner.live_async(
                strategy_cls,
                gateway_url=gateway_url,
                meta=meta,
                offline=offline,
            )
        )

    @staticmethod
    def offline(strategy_cls: type[Strategy]) -> Strategy:
        """Execute ``strategy_cls`` locally without Gateway interaction."""
        return asyncio.run(Runner.offline_async(strategy_cls))

    @staticmethod
    async def offline_async(strategy_cls: type[Strategy]) -> Strategy:
        strategy = Runner._prepare(strategy_cls)
        manager = Runner._init_tag_manager(strategy, None)
        logger.info(f"[OFFLINE] {strategy_cls.__name__} starting")
        Runner._apply_queue_map(strategy, {})
        await manager.resolve_tags(offline=True)
        await Runner._load_history(strategy, None, None)
        await Runner._replay_history(strategy, None, None)
        return strategy
