"""Sample strategy runnable in paper or live mode via env/YAML.

Environment variables
---------------------
- QMTL_TRADE_MODE: "paper" (default) or "live"
- QMTL_BROKER_URL: HTTP endpoint for live order submission
- QMTL_TRADE_MAX_RETRIES: integer (optional)
- QMTL_TRADE_BACKOFF: float seconds (optional)
- QMTL_WS_URL: WebSocket endpoint for live data/control (optional)
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

from qmtl.sdk import Strategy, StreamInput, Node, Runner, TradeExecutionService
from qmtl.transforms import (
    alpha_history_node,
    TradeSignalGeneratorNode,
    TradeOrderPublisherNode,
)
from qmtl.sdk.live_data_feed import WebSocketFeed


class SwitchableStrategy(Strategy):
    """Alpha->signal->order publisher pipeline with simple momentum alpha."""

    def setup(self) -> None:
        price = StreamInput(interval="60s", period=2)

        def compute_alpha(view: Any) -> float:
            data = view[price][price.interval]
            if len(data) < 2:
                return 0.0
            prev, last = data[-2][1]["close"], data[-1][1]["close"]
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
    url = os.getenv("QMTL_BROKER_URL", "").strip()
    if not url:
        raise RuntimeError("QMTL_BROKER_URL must be set for live mode")
    max_retries = int(os.getenv("QMTL_TRADE_MAX_RETRIES", "3"))
    try:
        backoff = float(os.getenv("QMTL_TRADE_BACKOFF", "0.1"))
    except ValueError:
        backoff = 0.1
    Runner.set_trade_execution_service(TradeExecutionService(url, max_retries=max_retries, backoff=backoff))


def main() -> None:
    mode = os.getenv("QMTL_TRADE_MODE", "paper").strip().lower()
    if mode not in {"paper", "live"}:
        raise ValueError("QMTL_TRADE_MODE must be 'paper' or 'live'")

    if mode == "live":
        _configure_live()
        ws_url = os.getenv("QMTL_WS_URL", "").strip()
        if ws_url:
            # Run a short-lived WS demo in parallel with the offline pass
            try:
                asyncio.run(_maybe_run_ws(ws_url))
            except Exception:
                pass

    # For simplicity, run an offline pass. In practice, you would call Runner.run
    # with gateway/world settings and maintain a persistent process.
    Runner.offline(SwitchableStrategy)


if __name__ == "__main__":
    main()

