"""Connector configuration example - QMTL v2.0.

QMTL v2 does not expose a client-side ``mode`` flag for submission. Execution
stage (backtest/paper/live) is governed by WorldService policy.

This example shows how a strategy module can read connector configuration (WS
URLs, broker URL) and wire optional integrations, while still submitting via
the single entry point: ``Runner.submit(strategy, world=...)``.
"""

from __future__ import annotations

import asyncio
from typing import Any

from qmtl.runtime.sdk import Runner, Strategy
from qmtl.runtime.sdk.node import Node, StreamInput
from qmtl.runtime.sdk.trade_execution_service import TradeExecutionService
from qmtl.runtime.sdk import configuration as sdk_configuration
from qmtl.runtime.sdk import runtime
from qmtl.runtime.sdk.live_data_feed import WebSocketFeed
from qmtl.runtime.transforms import (
    alpha_history_node,
    TradeSignalGeneratorNode,
    TradeOrderPublisherNode,
)

def _connectors_config():
    return sdk_configuration.get_connectors_config()


class SwitchableStrategy(Strategy):
    """Alpha->signal->order publisher pipeline with simple momentum alpha."""

    def setup(self) -> None:
        price = StreamInput(interval="60s", period=2)

        def compute_alpha(view: Any) -> float:
            data = view[price][price.interval]
            if len(data) < 2:
                return 0.0
            prev = float(data[-2][1]["close"])
            last = float(data[-1][1]["close"])
            return (last - prev) / prev

        alpha = Node(input=price, compute_fn=compute_alpha, name="alpha")
        history = alpha_history_node(alpha, window=30)
        signal = TradeSignalGeneratorNode(
            history, long_threshold=0.0, short_threshold=0.0
        )
        orders = TradeOrderPublisherNode(signal)
        self.add_nodes([price, alpha, history, signal, orders])


async def _maybe_run_ws(url: str) -> None:
    async def _on_msg(data: dict) -> None:  # demo: print minimal updates
        kind = data.get("event") or data.get("type")
        if kind in {"queue_update", "activation"}:
            pass  # hook for stateful updates in real runs

    feed = WebSocketFeed(url, on_message=_on_msg)
    await feed.start()
    # For the demo, run briefly and stop. Real runners keep this alive.
    try:
        await asyncio.sleep(1.0)
    finally:
        await feed.stop()


def _configure_live() -> None:
    cfg = _connectors_config()
    url = (cfg.broker_url or "").strip()
    if not url:
        raise RuntimeError("connectors.broker_url must be set for the live domain")
    max_retries = int(cfg.trade_max_retries)
    backoff = float(cfg.trade_backoff)
    Runner.set_trade_execution_service(
        TradeExecutionService(url, max_retries=max_retries, backoff=backoff)
    )


def main() -> None:
    runtime.reload()
    cfg = _connectors_config()
    if (cfg.broker_url or "").strip():
        _configure_live()
    ws_url = (cfg.ws_url or "").strip()
    if ws_url:
        try:
            asyncio.run(_maybe_run_ws(ws_url))
        except Exception:
            pass

    # v2 API: single entry point; stage/mode is WorldService-governed
    result = Runner.submit(SwitchableStrategy)
    print(f"Strategy submitted: {result.status}")


if __name__ == "__main__":
    main()
