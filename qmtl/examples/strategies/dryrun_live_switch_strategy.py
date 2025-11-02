"""Sample strategy runnable in dryrun or live domains via YAML configuration.

Configuration excerpt::

    connectors:
      execution_domain: dryrun  # or "live"
      broker_url: https://broker/api/orders
      trade_max_retries: 3
      trade_backoff: 0.1
      ws_url: wss://gateway/ws

Execution domains mirror WorldService decisions. When the policy engine
emits ``effective_mode="validate"`` the SDK maps it to the ``backtest``
domain (orders gated OFF). ``effective_mode="paper"`` now maps to the
``dryrun`` domain, which keeps broker hooks wired while still suppressing
real order placement unless explicitly enabled.
"""

from __future__ import annotations

import asyncio
from typing import Any

from qmtl.runtime.sdk import (
    Strategy,
    StreamInput,
    Node,
    Runner,
    TradeExecutionService,
)
from qmtl.runtime.sdk import configuration as sdk_configuration
from qmtl.runtime.sdk import runtime
from qmtl.runtime.sdk.live_data_feed import WebSocketFeed
from qmtl.runtime.transforms import (
    alpha_history_node,
    TradeSignalGeneratorNode,
    TradeOrderPublisherNode,
)

DEFAULT_EXECUTION_DOMAIN = "dryrun"


def _connectors_config():
    return sdk_configuration.get_unified_config().connectors


def _resolve_execution_domain() -> str:
    """Return the configured execution domain with legacy compatibility."""

    cfg = _connectors_config()
    raw = (cfg.execution_domain or DEFAULT_EXECUTION_DOMAIN).strip().lower()
    if raw == "paper":
        raw = "dryrun"

    if raw not in {"dryrun", "live"}:
        raise ValueError("Execution domain must be 'dryrun' or 'live'")

    return raw


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
    sdk_configuration.reload()
    runtime.reload()
    domain = _resolve_execution_domain()

    if domain == "live":
        _configure_live()
        ws_url = (_connectors_config().ws_url or "").strip()
        if ws_url:
            # Run a short-lived WS demo in parallel with the offline pass
            try:
                asyncio.run(_maybe_run_ws(ws_url))
            except Exception:
                pass

    # For simplicity, run an offline pass. In practice, you would call Runner.run
    # with gateway/world settings and maintain a persistent process. World decisions
    # that set ``effective_mode="validate"`` map to the ``backtest`` execution domain,
    # keeping order gates OFF until promotion.
    Runner.offline(SwitchableStrategy)


if __name__ == "__main__":
    main()
