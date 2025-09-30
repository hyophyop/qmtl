# Gateway Fills Webhook

The Gateway exposes an optional HTTP endpoint for brokers or executors to submit fill and cancel events. Accepted events are validated and forwarded to Kafka topic `trade.fills`.

## Endpoint

`POST /fills`

## Authentication

Provide one of:

- `Authorization: Bearer <jwt>` – JWT signed with the shared event secret. The token must include `aud="fills"` and identify the `world_id` and `strategy_id` claims.
- `X-Signature` – HMAC SHA256 signature of the request body using the secret configured via `QMTL_FILL_SECRET`. The world and strategy may be supplied via `X-World-ID` and `X-Strategy-ID` headers.

## Payload

Request bodies must conform to the [ExecutionFillEvent](order_events.md) schema. Unknown fields are ignored.

Example:

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

## Failure handling

- `400` – invalid JSON or payload fails schema validation.
- `401` – authentication failed or missing.
- `202` – event accepted and forwarded to Kafka.

Produced messages use key `world_id|strategy_id|symbol|order_id` and include the runtime fingerprint in Kafka headers.
