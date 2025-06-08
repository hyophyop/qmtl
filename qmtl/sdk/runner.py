from __future__ import annotations

import base64
import json
from typing import Optional

import httpx

from .strategy import Strategy


class Runner:
    """Execute strategies in various modes."""

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
    def feed_queue_data(node, queue_id: str, interval: int, timestamp: int, payload) -> None:
        """Insert queue data into a node's cache."""
        node.feed(queue_id, interval, timestamp, payload)

    @staticmethod
    def backtest(
        strategy_cls: type[Strategy],
        *,
        start_time=None,
        end_time=None,
        on_missing="skip",
        gateway_url: str | None = None,
        meta: Optional[dict] = None,
        offline: bool = False,
    ) -> Strategy:
        """Run strategy in backtest mode."""
        strategy = Runner._prepare(strategy_cls)
        print(f"[BACKTEST] {strategy_cls.__name__} from {start_time} to {end_time} on_missing={on_missing}")
        dag = strategy.serialize()
        print(f"Sending DAG to service: {[n['node_id'] for n in dag['nodes']]}")
        queue_map = {}
        offline = offline or not gateway_url
        if gateway_url and not offline:
            try:
                queue_map = Runner._post_gateway(
                    gateway_url=gateway_url,
                    dag=dag,
                    meta=meta,
                    run_type="backtest",
                )
            except httpx.RequestError:
                print(f"Warning: Gateway connection failed during backtest. Operating in offline mode.") # Consider using a proper logger
                offline = True
        Runner._apply_queue_map(strategy, queue_map if not offline else {})
        # Placeholder for backtest logic
        return strategy

    @staticmethod
    def dryrun(
        strategy_cls: type[Strategy], *, gateway_url: str | None = None, meta: Optional[dict] = None, offline: bool = False
    ) -> Strategy:
        """Run strategy in dry-run (paper trading) mode."""
        strategy = Runner._prepare(strategy_cls)
        print(f"[DRYRUN] {strategy_cls.__name__} starting")
        dag = strategy.serialize()
        print(f"Sending DAG to service: {[n['node_id'] for n in dag['nodes']]}")
        queue_map = {}
        offline = offline or not gateway_url
        if gateway_url and not offline:
            try:
                queue_map = Runner._post_gateway(
                    gateway_url=gateway_url,
                    dag=dag,
                    meta=meta,
                    run_type="dry-run",
                )
            except httpx.RequestError:
                offline = True
        Runner._apply_queue_map(strategy, queue_map if not offline else {})
        # Placeholder for dry-run logic
        return strategy

    @staticmethod
    def live(
        strategy_cls: type[Strategy], *, gateway_url: str | None = None, meta: Optional[dict] = None, offline: bool = False
    ) -> Strategy:
        """Run strategy in live trading mode."""
        strategy = Runner._prepare(strategy_cls)
        print(f"[LIVE] {strategy_cls.__name__} starting")
        dag = strategy.serialize()
        print(f"Sending DAG to service: {[n['node_id'] for n in dag['nodes']]}")
        queue_map = {}
        offline = offline or not gateway_url
        if gateway_url and not offline:
            try:
                queue_map = Runner._post_gateway(
                    gateway_url=gateway_url,
                    dag=dag,
                    meta=meta,
                    run_type="live",
                )
            except httpx.RequestError:
                offline = True
        Runner._apply_queue_map(strategy, queue_map if not offline else {})
        # Placeholder for live trading logic
        return strategy
