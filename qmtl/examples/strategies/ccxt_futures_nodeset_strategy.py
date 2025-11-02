"""Example strategy using the CCXT futures Node Set."""

from __future__ import annotations

import os

from qmtl.runtime.sdk import Strategy, StreamInput, Node
from qmtl.runtime.transforms import alpha_history_node, TradeSignalGeneratorNode
from qmtl.runtime.nodesets.recipes import make_ccxt_futures_nodeset


class CcxtFuturesNodeSetStrategy(Strategy):
    """Demo strategy wiring a signal through the CCXT futures Node Set."""

    def setup(self) -> None:  # pragma: no cover - illustrative example
        price = StreamInput(interval="60s", period=2)

        def compute_alpha(view):
            data = view[price][price.interval]
            if len(data) < 2:
                return 0.0
            prev = data[-2][1]["close"]
            last = data[-1][1]["close"]
            return (last - prev) / prev

        alpha = Node(input=price, compute_fn=compute_alpha, name="alpha")
        history = alpha_history_node(alpha, window=5)
        signal = TradeSignalGeneratorNode(
            history,
            long_threshold=0.0,
            short_threshold=0.0,
            size=1.0,
        )

        nodeset = make_ccxt_futures_nodeset(
            signal,
            "demo-world",
            exchange_id="binanceusdm",
            sandbox=bool(os.getenv("BINANCE_FUT_SANDBOX")),
            apiKey=os.getenv("BINANCE_FUT_API_KEY"),
            secret=os.getenv("BINANCE_FUT_API_SECRET"),
            leverage=5,
            margin_mode="cross",
            hedge_mode=True,
        )
        self.add_nodes([price, alpha, history, signal, nodeset])

