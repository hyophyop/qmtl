---
title: "Execution Layer Nodes"
tags: [architecture, execution, nodes]
author: "QMTL Team"
last_modified: 2025-12-15
---

{{ nav_links() }}

# Execution Layer Nodes

## 0. Purpose and Core Loop Position

- Purpose: Catalogue wrapper nodes for pre-trade checks, order sizing, execution, fill ingestion, portfolio updates, risk controls and timing gates in the execution layer.
- Core Loop position: Serves as a reference for the Core Loop’s “strategy execution and order routing” stage, showing how post-signal orders flow through the execution chain. In practice, strategies usually consume these via [exchange_node_sets.md](exchange_node_sets.md).

Wrapper nodes for pre-trade checks, order sizing, execution, fill ingestion,
portfolio updates, risk controls and timing gates. These classes bridge
strategy signals with exchange node sets described in
[exchange_node_sets.md](exchange_node_sets.md) and rely on helper modules
under `qmtl/runtime/sdk`.

Usage note
- In typical strategies you should attach a prebuilt Node Set (wrapper) rather than wiring these nodes one by one. The Node Set API provides a convenient, stable surface while allowing internal node composition to evolve.

## Fan‑in (Multi‑Upstream) Pattern

Nodes can subscribe to more than one upstream. This enables “fan‑in” patterns where a downstream node reads several inputs at once (e.g., a price stream and an indicator window) to make a combined decision.

```mermaid
graph LR
    price[price stream] --> alpha[alpha]
    alpha --> hist[alpha_history]
    price --> combine
    hist --> combine[combine (fan-in)]
    combine --> signal[trade_signal]
    signal --> orders[publish_orders]
    orders --> router[router]
    router --> micro[MicroBatch]
```

Example code (CacheView indexing uses the upstream node and its interval):

```python
from qmtl.runtime.sdk import Node, StreamInput
from qmtl.runtime.transforms import alpha_history_node, TradeSignalGeneratorNode
from qmtl.runtime.pipeline.execution_nodes import RouterNode
from qmtl.runtime.pipeline.micro_batch import MicroBatchNode

price = StreamInput(interval="60s", period=2)

def compute_alpha(view):
    data = view[price][price.interval]
    if len(data) < 2:
        return 0.0
    prev, last = data[-2][1]["close"], data[-1][1]["close"]
    return (last - prev) / prev

alpha = Node(input=price, compute_fn=compute_alpha, name="alpha")
history = alpha_history_node(alpha, window=30)

def alpha_with_trend_gate(view):
    hist_data = view[history][history.interval]
    price_data = view[price][price.interval]
    if not hist_data or not price_data:
        return None
    hist_series = hist_data[-1][1]  # list[float]
    closes = [row[1]["close"] for row in price_data]
    if len(closes) < 2:
        return hist_series
    # Gate positive alpha when price momentum is down
    trend_up = closes[-1] >= closes[-2]
    return hist_series if trend_up else [v if v <= 0.0 else 0.0 for v in hist_series]

combined = Node(
    input=[history, price],  # multi-upstream (fan-in)
    compute_fn=alpha_with_trend_gate,
    name="alpha_with_trend_gate",
    interval=history.interval,
    period=history.period,
)

signal = TradeSignalGeneratorNode(combined, long_threshold=0.0, short_threshold=0.0)
orders = TradeOrderPublisherNode(signal)
router = RouterNode(orders, route_fn=lambda o: "binance" if str(o.get("symbol","")) .upper().endswith("USDT") else "ibkr")
micro = MicroBatchNode(router)
```

Notes
- `Node(input=[...])`: pass any iterable of upstream nodes to create a fan‑in node.
- `view[upstream][upstream.interval]`: access the latest window for each upstream within `compute_fn`.
- Event‑time gating uses the slowest upstream watermark; late data handling follows the node’s `allowed_lateness`/`on_late` policy.

{{ nav_links() }}
