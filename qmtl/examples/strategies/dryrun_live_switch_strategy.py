"""Sample strategy runnable in dryrun or live domains via env/YAML.

Environment variables
---------------------
- QMTL_EXECUTION_DOMAIN: "dryrun" (default) or "live"
- QMTL_TRADE_MODE: legacy alias ("paper" → "dryrun")
- QMTL_BROKER_URL: HTTP endpoint for live order submission
- QMTL_TRADE_MAX_RETRIES: integer (optional)
- QMTL_TRADE_BACKOFF: float seconds (optional)
- QMTL_WS_URL: WebSocket endpoint for live data/control (optional)

Execution domains mirror WorldService decisions. When the policy engine
emits ``effective_mode="validate"`` the SDK maps it to the ``backtest``
domain (orders gated OFF). ``effective_mode="paper"`` now maps to the
``dryrun`` domain, which keeps broker hooks wired while still suppressing
real order placement unless explicitly enabled.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

from qmtl.runtime.sdk import Strategy, StreamInput, Node, Runner, TradeExecutionService
from qmtl.runtime.transforms import (
    alpha_history_node,
    TradeSignalGeneratorNode,
    TradeOrderPublisherNode,
)
from qmtl.runtime.sdk.live_data_feed import WebSocketFeed


DEFAULT_EXECUTION_DOMAIN = "dryrun"
EXECUTION_DOMAIN_ENV = "QMTL_EXECUTION_DOMAIN"
LEGACY_MODE_ENV = "QMTL_TRADE_MODE"


def _resolve_execution_domain() -> str:
    """Return the configured execution domain with legacy compatibility."""

    raw = os.getenv(EXECUTION_DOMAIN_ENV)
    if raw is None:
        raw = os.getenv(LEGACY_MODE_ENV)
    if raw is None:
        raw = DEFAULT_EXECUTION_DOMAIN

    domain = raw.strip().lower()
    if domain == "paper":
        domain = "dryrun"

    if domain not in {"dryrun", "live"}:
        raise ValueError("Execution domain must be 'dryrun' or 'live'")

    return domain


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
        raise RuntimeError("QMTL_BROKER_URL must be set for the live domain")
    max_retries = int(os.getenv("QMTL_TRADE_MAX_RETRIES", "3"))
    try:
        backoff = float(os.getenv("QMTL_TRADE_BACKOFF", "0.1"))
    except ValueError:
        backoff = 0.1
    Runner.set_trade_execution_service(TradeExecutionService(url, max_retries=max_retries, backoff=backoff))


def main() -> None:
    domain = _resolve_execution_domain()

    if domain == "live":
        _configure_live()
        ws_url = os.getenv("QMTL_WS_URL", "").strip()
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

