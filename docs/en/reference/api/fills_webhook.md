# Gateway Fills Webhook

The Gateway exposes an optional HTTP endpoint for brokers or executors to submit fill and cancel events. Accepted events are validated and forwarded to Kafka topic `trade.fills`.

## Endpoint

`POST /fills`

## Authentication

Provide one of:

- `Authorization: Bearer <jwt>` – JWT signed with the shared event secret. The token must include `aud="fills"` plus `world_id` and `strategy_id` claims.
- `X-Signature` – fallback auth used only when no Bearer header is present. Send an HMAC-SHA256 hex digest of the raw request body using `QMTL_FILL_SECRET`. Scope IDs are resolved from `X-World-ID` and `X-Strategy-ID` first, then from top-level body fields `world_id` and `strategy_id`.

## Payload

Request bodies must be a CloudEvents 1.0 envelope whose top-level `data` object conforms to the [ExecutionFillEvent](order_events.md) schema. Unknown fields inside `ExecutionFillEvent` are ignored.

Example:

```json
{
  "specversion": "1.0",
  "id": "exch-7890-12",
  "type": "qmtl.trade.fill",
  "source": "broker/binanceusdm",
  "time": "2025-09-08T00:00:01.100Z",
  "world_id": "arch_world",
  "strategy_id": "strat_001",
  "data": {
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
}
```

## Failure handling

- `400` – invalid JSON (`E_INVALID_JSON`), missing CloudEvents envelope (`E_CE_REQUIRED`), unresolved `world_id`/`strategy_id` (`E_MISSING_IDS`), or schema validation failure in `data` (`E_SCHEMA_INVALID`).
- `401` – authentication missing/invalid (`E_AUTH`).
- `202` – event accepted and forwarded to Kafka.

Produced messages use key `world_id|strategy_id|symbol|order_id` and include the runtime fingerprint in Kafka headers.
