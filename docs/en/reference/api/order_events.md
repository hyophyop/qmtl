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

## Schemas

Formal JSON Schemas are available in `reference/schemas` and can be
registered programmatically with `qmtl.foundation.schema.register_order_schemas`.

OrderPayload
```json
{
  "world_id": "arch_world",
  "strategy_id": "strat_001",
  "correlation_id": "ord-20230907-0001", 
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
  "correlation_id": "ord-20230907-0001",
  "symbol": "BTC/USDT",
  "side": "BUY",
  "quantity": 0.005,
  "price": 24990.5,
  "commission": 0.02,
  "slippage": 0.5,
  "market_impact": 0.0,
  "tif": "GTC",
  "fill_time": 1694102401100,
  "status": "partially_filled",
  "seq": 12,
  "etag": "w1-s1-7890-12"
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

### CloudEvents Envelope (Optional)

Webhook and internal event transport MAY wrap payloads in CloudEvents 1.0:

```json
{
  "specversion": "1.0",
  "type": "qmtl.trade.fill",
  "source": "broker/binanceusdm",
  "id": "exch-7890-12",
  "time": "2025-09-08T00:00:01.100Z",
  "datacontenttype": "application/json",
  "data": { /* ExecutionFillEvent */ }
}
```

Consumers MUST accept both bare and CloudEvents-wrapped forms.

## Gateway `/fills` Webhook

The Gateway exposes a `/fills` endpoint for broker callbacks. Payloads may be
sent as a raw `ExecutionFillEvent` or wrapped in a CloudEvents 1.0 envelope.
Requests must include a HMAC-signed JWT whose `world_id` and `strategy_id`
claims match the payload. Out-of-scope requests are rejected.

### Replay Endpoint

The current Gateway implementation exposes only a placeholder
`GET /fills/replay` endpoint; replay delivery is not implemented yet. The route
returns `202 Accepted` with the message `"replay not implemented in this build"`.

{{ nav_links() }}
