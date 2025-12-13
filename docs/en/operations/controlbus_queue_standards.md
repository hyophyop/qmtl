# ControlBus / Queue Operational Standards

This document defines topic naming, consumer groups, retry/DLQ behavior, and idempotency rules so ControlBus (Kafka) producers/consumers remain **idempotent, observable, and re-playable** at operational scale.

## Topic and Event Types

- WorldService publishes/consumes CloudEvents on `worldservice.server.controlbus_topic` (default: `policy`).
- Multiple event types may share the same topic; consumers must filter on CloudEvents `type`.
  - Examples: `risk_snapshot_updated`, `policy_updated`, `activation_updated`, `evaluation_run_created`, `evaluation_run_updated`

## Consumer Groups (Recommended)

- RiskHub snapshot consumer: `worldservice-risk-hub`
  - Processes only `risk_snapshot_updated` events.

## Retry / Backoff / DLQ Defaults

### Consumer (RiskHubControlBusConsumer)
- `max_attempts`: 3
- `retry_backoff_sec`: 0.5
- `dlq_topic`: enable explicitly in operations when needed (e.g., `${controlbus_topic}.dlq`)
  - DLQ event type: `risk_snapshot_updated_dlq`

### Producers (ControlBusProducer / RiskHubClient)
- Producers should implement retries/backoff and expose failures via logs/metrics.
- For large RiskHub snapshot payloads (above the offload threshold), prefer ref-based offload:
  - `covariance_ref`, `realized_returns_ref`, `stress_ref`

## Idempotency / Dedupe Rules

### RiskHub snapshots
- Consumer dedupe key: `risk_snapshot_dedupe_key(payload)`
  - Built from `(world_id, version, hash, actor, stage)`
- Producers must enforce:
  - `provenance.actor` (or `X-Actor`) is required
  - `provenance.stage` (or `X-Stage`) is strongly recommended (backtest/paper/live separation)
  - `hash` must follow stable hashing rules so retries produce the same digest

### ControlBus events (general)
- CloudEvents `correlation_id` groups retries and related events (e.g., the same EvaluationRun).
- If `data.idempotency_key` is present, consumers should use it to prevent duplicate side effects.

## Observability Checklist

Example WorldService Prometheus metrics:

- `risk_hub_snapshot_processed_total{world_id,stage}`
- `risk_hub_snapshot_failed_total{world_id,stage}`
- `risk_hub_snapshot_retry_total{world_id,stage}`
- `risk_hub_snapshot_dlq_total{world_id,stage}`
- `risk_hub_snapshot_dedupe_total{world_id,stage}`
- `risk_hub_snapshot_expired_total{world_id,stage}`

## Required Rehearsal Scenarios

- Re-processing duplicate events (dedupe hit) increases counters
- Dropping expired snapshots (TTL) is observable
- Fail → retry(backoff) → success, or fail → DLQ routing
- Stage labels (backtest/paper/live) remain separated in metrics

