---
title: "Order & Fill Event Schemas"
tags: [api, events]
author: "QMTL Team"
last_modified: 2025-09-08
---

{{ nav_links() }}

# Order & Fill Event Schemas

This page standardizes minimal JSON shapes for orders, acks/status, and fills used by Exchange Node Sets. These schemas complement the Brokerage API and Connectors.

## Topics & Keys

- `trade.orders` (append‑only)
  - key: `world_id|strategy_id|symbol|client_order_id` (or deterministic hash)
  - value: `OrderPayload`

- `trade.fills` (append‑only)
  - key: `world_id|strategy_id|symbol|order_id`
  - value: `ExecutionFillEvent`

- `trade.portfolio` (compacted)
  - key: `world_id|[strategy_id]|snapshot`
  - value: `PortfolioSnapshot`

Partitioning: Choose keys to keep per‑strategy (or per‑world) order while allowing horizontal scale. Compaction is only for snapshots.

## Schemas (informal)

OrderPayload
```json
{
  "world_id": "arch_world",
  "strategy_id": "strat_001",
  "symbol": "BTC/USDT",
  "side": "BUY",             // BUY | SELL
  "type": "limit",           // market | limit | stop | stop_limit
  "quantity": 0.01,
  "limit_price": 25000.0,
  "stop_price": null,
  "time_in_force": "GTC",    // DAY | GTC | IOC | FOK
  "client_order_id": "c-abc123",
  "timestamp": 1694102400000,
  "reduce_only": false,
  "position_side": null,      // LONG | SHORT (futures)
  "metadata": {"source": "node_set/binance_spot"}
}
```

OrderAck / Status
```json
{
  "order_id": "exch-7890",
  "client_order_id": "c-abc123",
  "status": "accepted",      // accepted | rejected | canceled | filled | partially_filled | expired
  "reason": null,
  "broker": "binance",
  "raw": {"provider_payload": "..."}
}
```

ExecutionFillEvent
```json
{
  "order_id": "exch-7890",
  "client_order_id": "c-abc123",
  "symbol": "BTC/USDT",
  "side": "BUY",
  "quantity": 0.005,
  "price": 24990.5,
  "commission": 0.02,
  "slippage": 0.5,
  "market_impact": 0.0,
  "tif": "GTC",
  "fill_time": 1694102401100,
  "status": "partially_filled"
}
```

PortfolioSnapshot (compacted)
```json
{
  "world_id": "arch_world",
  "strategy_id": "strat_001",
  "as_of": 1694102402000,
  "cash": 100000.0,
  "positions": {
    "BTC/USDT": {"qty": 0.01, "avg_cost": 25010.0, "mark": 24995.0}
  },
  "metrics": {"exposure": 0.25, "leverage": 1.1}
}
```

## Notes

- Time‑in‑force semantics align with Execution State doc.
- `client_order_id` is optional but recommended for idempotency and reconciliation.
- Providers may add fields in `metadata` or `raw`; downstream consumers should ignore unknown keys.

{{ nav_links() }}

