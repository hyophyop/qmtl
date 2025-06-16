from __future__ import annotations

import base64
import json
import asyncio
import time
from typing import Optional, Iterable

import httpx

from .strategy import Strategy
from .tagquery_manager import TagQueryManager

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

    _ray_available = ray is not None
    _kafka_available = AIOKafkaConsumer is not None

    # ------------------------------------------------------------------

    @staticmethod
    def _execute_compute_fn(fn, cache_view) -> None:
        """Run ``fn`` using Ray when available."""
        if Runner._ray_available:
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
    ) -> dict:
        url = gateway_url.rstrip("/") + "/strategies"
        from qmtl.common import crc32_of_list

        payload = {
            "dag_json": base64.b64encode(json.dumps(dag).encode()).decode(),
            "meta": meta,
            "run_type": run_type,
            "node_ids_crc32": crc32_of_list(n["node_id"] for n in dag.get("nodes", [])),
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=payload)
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
        node.cache.append(queue_id, interval, timestamp, payload)
        if node.pre_warmup and node.cache.ready():
            node.pre_warmup = False
        missing = node.cache.missing_flags().get(queue_id, {}).get(interval, False)
        if missing:
            if on_missing == "fail":
                raise RuntimeError("gap detected")
            if on_missing == "skip":
                return
        result = None
        if not node.pre_warmup and node.compute_fn and node.execute:
            if Runner._ray_available:
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
        print(f"[BACKTEST] {strategy_cls.__name__} from {start_time} to {end_time} on_missing={on_missing}")
        dag = strategy.serialize()
        print(f"Sending DAG to service: {[n['node_id'] for n in dag['nodes']]}")
        if not gateway_url:
            raise RuntimeError("gateway_url is required for backtest mode")

        try:
            queue_map = await Runner._post_gateway_async(
                gateway_url=gateway_url,
                dag=dag,
                meta=meta,
                run_type="backtest",
            )
        except httpx.RequestError as exc:
            raise RuntimeError("failed to connect to Gateway") from exc

        Runner._apply_queue_map(strategy, queue_map)
        await manager.resolve_tags(offline=False)
        await Runner._ensure_history(strategy, start_time, end_time)
        # Placeholder for backtest logic
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
    ) -> Strategy:
        """Run strategy in dry-run (paper trading) mode. Requires ``gateway_url``."""
        strategy = Runner._prepare(strategy_cls)
        manager = Runner._init_tag_manager(strategy, gateway_url)
        print(f"[DRYRUN] {strategy_cls.__name__} starting")
        dag = strategy.serialize()
        print(f"Sending DAG to service: {[n['node_id'] for n in dag['nodes']]}")

        if not gateway_url:
            raise RuntimeError("gateway_url is required for dry-run mode")

        try:
            queue_map = await Runner._post_gateway_async(
                gateway_url=gateway_url,
                dag=dag,
                meta=meta,
                run_type="dry-run",
            )
        except httpx.RequestError as exc:
            raise RuntimeError("failed to connect to Gateway") from exc

        Runner._apply_queue_map(strategy, queue_map)
        await manager.resolve_tags(offline=False)
        await Runner._ensure_history(strategy, None, None, stop_on_ready=True)
        # Placeholder for dry-run logic
        return strategy

    def dryrun(
        strategy_cls: type[Strategy],
        *,
        gateway_url: str | None = None,
        meta: Optional[dict] = None,
    ) -> Strategy:
        return asyncio.run(
            Runner.dryrun_async(
                strategy_cls,
                gateway_url=gateway_url,
                meta=meta,
            )
        )

    @staticmethod
    async def live_async(
        strategy_cls: type[Strategy],
        *,
        gateway_url: str | None = None,
        meta: Optional[dict] = None,
    ) -> Strategy:
        """Run strategy in live trading mode. Requires ``gateway_url``."""
        strategy = Runner._prepare(strategy_cls)
        manager = Runner._init_tag_manager(strategy, gateway_url)
        print(f"[LIVE] {strategy_cls.__name__} starting")
        dag = strategy.serialize()
        print(f"Sending DAG to service: {[n['node_id'] for n in dag['nodes']]}")

        if not gateway_url:
            raise RuntimeError("gateway_url is required for live mode")

        try:
            queue_map = await Runner._post_gateway_async(
                gateway_url=gateway_url,
                dag=dag,
                meta=meta,
                run_type="live",
            )
        except httpx.RequestError as exc:
            raise RuntimeError("failed to connect to Gateway") from exc

        Runner._apply_queue_map(strategy, queue_map)
        await manager.resolve_tags(offline=False)
        await Runner._ensure_history(strategy, None, None, stop_on_ready=True)
        await manager.start()
        
        # Placeholder for live trading logic
        return strategy

    @staticmethod
    def live(
        strategy_cls: type[Strategy],
        *,
        gateway_url: str | None = None,
        meta: Optional[dict] = None,
    ) -> Strategy:
        return asyncio.run(
            Runner.live_async(
                strategy_cls,
                gateway_url=gateway_url,
                meta=meta,
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
        print(f"[OFFLINE] {strategy_cls.__name__} starting")
        Runner._apply_queue_map(strategy, {})
        await manager.resolve_tags(offline=True)
        await Runner._load_history(strategy, None, None)
        # Placeholder for offline execution logic
        return strategy
