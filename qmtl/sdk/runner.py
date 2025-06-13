from __future__ import annotations

import base64
import json
import asyncio
from typing import Optional

import httpx

from .strategy import Strategy
from .backfill import BackfillSource, QuestDBSource

try:  # Optional Ray dependency
    import ray  # type: ignore
except Exception:  # pragma: no cover - Ray not installed
    ray = None  # type: ignore


class Runner:
    """Execute strategies in various modes."""

    _ray_available = ray is not None

    # ------------------------------------------------------------------
    @staticmethod
    def _create_backfill_source(spec: str) -> BackfillSource:
        """Return BackfillSource instance for ``spec``."""
        if spec.startswith("questdb:"):
            dsn = spec.split(":", 1)[1]
            return QuestDBSource(dsn)
        raise RuntimeError("unsupported backfill source")

    @staticmethod
    async def _run_backfill(
        strategy: Strategy,
        source: BackfillSource,
        start: int,
        end: int,
    ) -> None:
        async def _backfill_node(node):
            if node.interval is None:
                return
            df = await asyncio.to_thread(
                source.fetch,
                start,
                end,
                node_id=node.node_id,
                interval=node.interval,
            )
            if df is None:
                return
            items = []
            for _, row in df.iterrows():
                ts = int(row.get("ts", 0))
                items.append((ts, row.to_dict()))
            node.cache.backfill_bulk(node.node_id, node.interval, items)

        tasks = [asyncio.create_task(_backfill_node(n)) for n in strategy.nodes]
        if tasks:
            await asyncio.gather(*tasks)

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
    def _post_gateway(
        *,
        gateway_url: str,
        dag: dict,
        meta: Optional[dict],
        run_type: str,
    ) -> dict:
        url = gateway_url.rstrip("/") + "/strategies"
        payload = {
            "dag_json": base64.b64encode(json.dumps(dag).encode()).decode(),
            "meta": meta,
            "run_type": run_type,
        }
        resp = httpx.post(url, json=payload)
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
        strategy.define_execution()
        return strategy

    @staticmethod
    def _apply_queue_map(strategy: Strategy, queue_map: dict[str, str]) -> None:
        for node in strategy.nodes:
            topic = queue_map.get(node.node_id)
            if topic:
                node.execute = False
                node.queue_topic = topic
            else:
                node.execute = True
                node.queue_topic = None

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
    ) -> None:
        """Insert queue data into ``node`` and trigger its ``compute_fn``."""
        node.cache.append(queue_id, interval, timestamp, payload)
        if node.pre_warmup and node.cache.ready():
            node.pre_warmup = False
        missing = node.cache.missing_flags().get(queue_id, {}).get(interval, False)
        if missing:
            if on_missing == "fail":
                raise RuntimeError("gap detected")
            if on_missing == "skip":
                return
        if not node.pre_warmup and node.compute_fn:
            Runner._execute_compute_fn(node.compute_fn, node.cache.view())

    @staticmethod
    def backtest(
        strategy_cls: type[Strategy],
        *,
        start_time=None,
        end_time=None,
        on_missing="skip",
        gateway_url: str | None = None,
        meta: Optional[dict] = None,
        backfill_source: str | None = None,
        backfill_start: int | None = None,
        backfill_end: int | None = None,
    ) -> Strategy:
        """Run strategy in backtest mode. Requires ``gateway_url``."""
        strategy = Runner._prepare(strategy_cls)
        print(f"[BACKTEST] {strategy_cls.__name__} from {start_time} to {end_time} on_missing={on_missing}")
        dag = strategy.serialize()
        print(f"Sending DAG to service: {[n['node_id'] for n in dag['nodes']]}")
        if not gateway_url:
            raise RuntimeError("gateway_url is required for backtest mode")

        try:
            queue_map = Runner._post_gateway(
                gateway_url=gateway_url,
                dag=dag,
                meta=meta,
                run_type="backtest",
            )
        except httpx.RequestError as exc:
            raise RuntimeError("failed to connect to Gateway") from exc

        Runner._apply_queue_map(strategy, queue_map)
        if backfill_source and backfill_start is not None and backfill_end is not None:
            src = Runner._create_backfill_source(backfill_source)
            asyncio.run(Runner._run_backfill(strategy, src, backfill_start, backfill_end))
        # Placeholder for backtest logic
        return strategy

    @staticmethod
    def dryrun(
        strategy_cls: type[Strategy], *, gateway_url: str | None = None, meta: Optional[dict] = None
        , backfill_source: str | None = None, backfill_start: int | None = None, backfill_end: int | None = None
    ) -> Strategy:
        """Run strategy in dry-run (paper trading) mode. Requires ``gateway_url``."""
        strategy = Runner._prepare(strategy_cls)
        print(f"[DRYRUN] {strategy_cls.__name__} starting")
        dag = strategy.serialize()
        print(f"Sending DAG to service: {[n['node_id'] for n in dag['nodes']]}")

        if not gateway_url:
            raise RuntimeError("gateway_url is required for dry-run mode")

        try:
            queue_map = Runner._post_gateway(
                gateway_url=gateway_url,
                dag=dag,
                meta=meta,
                run_type="dry-run",
            )
        except httpx.RequestError as exc:
            raise RuntimeError("failed to connect to Gateway") from exc

        Runner._apply_queue_map(strategy, queue_map)
        if backfill_source and backfill_start is not None and backfill_end is not None:
            src = Runner._create_backfill_source(backfill_source)
            asyncio.run(Runner._run_backfill(strategy, src, backfill_start, backfill_end))
        # Placeholder for dry-run logic
        return strategy

    @staticmethod
    def live(
        strategy_cls: type[Strategy], *, gateway_url: str | None = None, meta: Optional[dict] = None,
        backfill_source: str | None = None, backfill_start: int | None = None, backfill_end: int | None = None
    ) -> Strategy:
        """Run strategy in live trading mode. Requires ``gateway_url``."""
        strategy = Runner._prepare(strategy_cls)
        print(f"[LIVE] {strategy_cls.__name__} starting")
        dag = strategy.serialize()
        print(f"Sending DAG to service: {[n['node_id'] for n in dag['nodes']]}")

        if not gateway_url:
            raise RuntimeError("gateway_url is required for live mode")

        try:
            queue_map = Runner._post_gateway(
                gateway_url=gateway_url,
                dag=dag,
                meta=meta,
                run_type="live",
            )
        except httpx.RequestError as exc:
            raise RuntimeError("failed to connect to Gateway") from exc

        Runner._apply_queue_map(strategy, queue_map)
        if backfill_source and backfill_start is not None and backfill_end is not None:
            src = Runner._create_backfill_source(backfill_source)
            asyncio.run(Runner._run_backfill(strategy, src, backfill_start, backfill_end))
        # Placeholder for live trading logic
        return strategy

    @staticmethod
    def offline(strategy_cls: type[Strategy]) -> Strategy:
        """Execute ``strategy_cls`` locally without Gateway interaction."""
        strategy = Runner._prepare(strategy_cls)
        print(f"[OFFLINE] {strategy_cls.__name__} starting")
        Runner._apply_queue_map(strategy, {})
        # Placeholder for offline execution logic
        return strategy
