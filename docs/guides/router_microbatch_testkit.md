# RouterNode, MicroBatchNode, and Node Set Test Kit — How to Use

This short guide shows how to route orders to different targets, micro‑batch payloads, and quickly attach a Node Set in tests.

## RouterNode

Route orders by computing a `route` key (e.g., exchange) from each order. Downstream connectors branch on `order["route"]`.

```python
from qmtl.runtime.pipeline.execution_nodes import RouterNode

def route_fn(order: dict) -> str:
    sym = order.get("symbol", "")
    return "binance" if str(sym).upper().endswith("USDT") else "ibkr"

routed = RouterNode(orders, route_fn=route_fn)
```

## MicroBatchNode

Reduce per‑item overhead by emitting a list of payloads for the latest complete bucket. The node flushes the previous bucket when a new timestamp arrives.

```python
from qmtl.runtime.pipeline.micro_batch import MicroBatchNode

batches = MicroBatchNode(routed)
# Example batch shape: [{"symbol": "BTCUSDT", ...}, {"symbol": "ETHUSDT", ...}]
```

See also: Architecture → Exchange Node Sets for where to place batching in the chain: [architecture/exchange_node_sets.md](../architecture/exchange_node_sets.md)

## Node Set Test Kit

Attach a Node Set behind a signal in tests and create fake fill events for webhook simulation.

```python
from qmtl.runtime.nodesets.base import NodeSetBuilder
from qmtl.runtime.nodesets.testkit import attach_minimal, fake_fill_webhook

ns = attach_minimal(NodeSetBuilder(), signal, world_id="demo")
evt = fake_fill_webhook("AAPL", 1.0, 10.0)
assert evt["type"] == "trade.fill" and evt["data"]["symbol"] == "AAPL"
```

For a complete example chain, see: `qmtl/examples/strategies/order_pipeline_strategy.py`.

