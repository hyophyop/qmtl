# Node Set Portfolio Scope

This guide shows how to configure a Node Set to share portfolio state across strategies within the same world (world scope) or keep it isolated per strategy (strategy scope).

See Exchange Node Sets architecture for the end‑to‑end design: ../architecture/exchange_node_sets.md

## Usage

```python
from qmtl.nodesets import NodeSetBuilder
from qmtl.nodesets.options import NodeSetOptions
from qmtl.sdk import Strategy, StreamInput, Node
from qmtl.transforms import TradeSignalGeneratorNode


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

        # world scope shares portfolio across strategies in the same world
        opts = NodeSetOptions(portfolio_scope="world")
        nodeset = NodeSetBuilder(options=opts).attach(signal, world_id="demo", scope="world")

        # Add the execution chain behind the signal
        self.add_nodes([
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
        ])
```

Notes
- strategy (default) scopes portfolio snapshots and fills by `(world_id, strategy_id, symbol)`.
- world scopes by `(world_id, symbol)` so multiple strategies share cash/limits.
- In the current scaffold, this option establishes the contract; concrete exchange Node Sets enforce the behavior as they are implemented.

