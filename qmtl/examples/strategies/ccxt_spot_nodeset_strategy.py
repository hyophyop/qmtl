"""Example strategy using the CCXT spot Node Set."""

from __future__ import annotations

import os

from qmtl.sdk import Strategy, StreamInput, Node
from qmtl.transforms import alpha_history_node, TradeSignalGeneratorNode
from qmtl.nodesets.recipes import make_ccxt_spot_nodeset


class CcxtSpotNodeSetStrategy(Strategy):
    """Demo strategy wiring a signal through the CCXT spot Node Set."""

    def setup(self) -> None:
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
            history, long_threshold=0.0, short_threshold=0.0, size=1.0
        )

        nodeset = make_ccxt_spot_nodeset(
            signal,
            "demo-world",
            exchange_id="binance",
            sandbox=bool(os.getenv("BINANCE_SANDBOX")),
            apiKey=os.getenv("BINANCE_API_KEY"),
            secret=os.getenv("BINANCE_API_SECRET"),
        )
        self.add_nodes([price, alpha, history, signal, nodeset])
