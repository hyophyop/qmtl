"""Example strategy wiring a Node Set with world-scoped portfolio.

This demonstrates how multiple strategies in the same world can share
portfolio state by setting portfolio_scope="world". The current scaffold
uses stub nodes to establish the contract.
"""

from __future__ import annotations

from qmtl.sdk import Strategy, StreamInput, Node
from qmtl.transforms import TradeSignalGeneratorNode
from qmtl.nodesets.base import NodeSetBuilder
from qmtl.nodesets.options import NodeSetOptions


class WorldScopeNodeSetStrategy(Strategy):
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
        signal = TradeSignalGeneratorNode(
            alpha, long_threshold=0.0, short_threshold=0.0, size=1.0
        )

        opts = NodeSetOptions(portfolio_scope="world")
        nodeset = NodeSetBuilder(options=opts).attach(signal, world_id="demo", scope="world")

        self.add_nodes(
            [
                price,
                alpha,
                signal,
                nodeset.pretrade,
                nodeset.sizing,
                nodeset.execution,
                nodeset.fills,
                nodeset.portfolio,
                nodeset.risk,
                nodeset.timing,
            ]
        )

