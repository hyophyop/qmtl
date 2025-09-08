Title: Gateway: /fills Webhook → Kafka (trade.fills)
Labels: gateway, feature, security

Summary
Add an optional webhook on Gateway to accept authenticated fill/cancel events from brokers/executors and forward to `trade.fills`.

Tasks
- Route: `POST /fills`
  - Auth: JWT or HMAC signature verification; world-/strategy-scoped RBAC.
  - Validate against `ExecutionFillEvent` shape; drop/flag unknown fields.
- Produce to Kafka
  - Topic `trade.fills`, key `world_id|strategy_id|symbol|order_id`.
  - Include runtime fingerprint header when possible.
- Docs & Runbook
  - Security guidance, example payloads, failure handling.

Acceptance Criteria
- End-to-end demo: POST → Kafka → FillIngestNode → Portfolio updates.
- Metrics and structured logs emitted on accept/reject.

