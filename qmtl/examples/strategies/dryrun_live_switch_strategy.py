"""Mode-based strategy example - QMTL v2.0.

Demonstrates the simplified v2 Mode concept:
- Mode.BACKTEST: Historical data simulation
- Mode.PAPER: Real-time data, simulated orders  
- Mode.LIVE: Real-time data, real orders

Configuration via environment variables:
  QMTL_GATEWAY_URL     Gateway URL (auto-discovered)
  QMTL_DEFAULT_WORLD   Default world (auto-discovered)
"""

from __future__ import annotations

import asyncio
from typing import Any

from qmtl.runtime.sdk import Runner, Strategy, Mode
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

DEFAULT_MODE = Mode.PAPER


def _connectors_config():
    return sdk_configuration.get_connectors_config()


def _resolve_mode() -> Mode:
    """Return the configured mode from environment or config."""
    cfg = _connectors_config()
    raw = (cfg.execution_domain or "paper").strip().lower()
    
    # Map legacy domain names to v2 Mode
    mode_map = {
        "backtest": Mode.BACKTEST,
        "dryrun": Mode.PAPER,
        "paper": Mode.PAPER,
        "live": Mode.LIVE,
    }
    return mode_map.get(raw, DEFAULT_MODE)


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
    mode = _resolve_mode()

    if mode == Mode.LIVE:
        _configure_live()
        ws_url = (_connectors_config().ws_url or "").strip()
        if ws_url:
            try:
                asyncio.run(_maybe_run_ws(ws_url))
            except Exception:
                pass

    # v2 API: Single entry point with mode
    result = Runner.submit(SwitchableStrategy, mode=mode)
    print(f"Strategy submitted: {result.status}")


if __name__ == "__main__":
    main()
