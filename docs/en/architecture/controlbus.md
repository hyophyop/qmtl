---
title: "ControlBus — Internal Control Bus (Opaque to SDK)"
tags: [architecture, events, control]
author: "QMTL Team"
last_modified: 2026-02-06
spec_version: v1.0
---

{{ nav_links() }}

# ControlBus — Internal Control Bus

Related: [WorldService](worldservice.md)  
Related: [ACK/Gap Resync RFC (Draft)](ack_resync_rfc.md)

ControlBus distributes control‑plane updates (not data) from core services to Gateways. It is an internal component and not a public API; SDKs never connect directly in the default deployment. All control events are versioned envelopes and include `type` and `version` fields.

## 0. Role & Non‑Goals

Role
- Fan‑out of ActivationUpdated, PolicyUpdated, QueueUpdated events
- Partitioned streams per world_id or (tags, interval) to preserve per‑key ordering
- Bounded retention with compacted history for late subscribers

Non‑Goals
- Not a source of truth (SSOT); decisions/activation live in WorldService, queues in DAG Manager
- Not a general data bus; market/indicator/trade data remain on data topics managed by DAG Manager

!!! note "Design intent"
- ControlBus is opaque to SDKs by default. Clients consume control events only via the Gateway’s tokenized WebSocket bridge (`/events/subscribe`). This keeps the bus private, centralizes authN/Z, and allows initial snapshot/state_hash reconciliation without exposing internal topics.

!!! warning "Deployment profiles"
- **prod**: ControlBus is mandatory. Gateway, WorldService, and DAG Manager fail fast if brokers/topics are missing or if the Kafka client is unavailable.
- **dev**: ControlBus may be disabled for local runs. Publishers/consumers emit warnings and skip I/O, meaning no control events will be produced or consumed.

---

## 1. Topology & Semantics

- Transport: Kafka/Redpanda recommended, or equivalent pub/sub. Topic names are provided via deployment/service configuration; `control.*` is a recommended namespace.
- Topics (example: a split-topic layout that Gateway subscribes to)
  - `activation` partitioned by `world_id`
  - `control.activation.ack` partitioned by `world_id` (activation acknowledgements)
  - `queue` partitioned by `",".join(tags)` (Gateway preserves ordering per tag combination)
  - `policy` partitioned by `world_id`
  - `sentinel_weight` partitioned by `sentinel_id`
- Ordering: guaranteed within partition only; consumers must handle duplicates and gaps
- Delivery: at‑least‑once; idempotent consumers via `etag`/`run_id`

---

## 2. Event Schemas

ActivationUpdated (versioned)
```json
{
  "type": "ActivationUpdated",
  "version": 1,
  "world_id": "crypto_mom_1h",
  "strategy_id": "abcd",
  "side": "long",
  "active": true,
  "weight": 1.0,
  "freeze": false,
  "drain": false,
  "etag": "act:crypto_mom_1h:abcd:long:42",
  "run_id": "7a1b4c...",
  "ts": "2025-08-28T09:00:00Z",
  "state_hash": "blake3:...",
  "phase": "unfreeze",
  "requires_ack": true,
  "sequence": 17
}
```

- `phase` is either `freeze` or `unfreeze` and is populated by [`ActivationEventPublisher.update_activation_state`]({{ code_url('qmtl/services/worldservice/activation.py#L58') }}).
- `requires_ack=true` means Gateway MUST apply only contiguous sequences per `(world_id, run_id)` and publish an acknowledgement for each applied `sequence` via the ControlBus response channel. This is Gateway transport/apply acknowledgement, not end-to-end acknowledgement from every downstream SDK/WebSocket client and not proof that order-flow reopening completed.
- `sequence` is the per-run monotonic counter produced by [`ApplyRunState.next_sequence()`]({{ code_url('qmtl/services/worldservice/run_state.py#L47') }}). In the current Gateway consumer implementation: `sequence < next_sequence` is dropped as duplicate, `sequence > next_sequence` is buffered (ACK/relay deferred), and `sequence == next_sequence` is processed while contiguous buffered events are flushed in order.

ActivationAck (versioned)
```json
{
  "type": "ActivationAck",
  "version": 1,
  "world_id": "crypto_mom_1h",
  "run_id": "7a1b4c...",
  "sequence": 17,
  "phase": "unfreeze",
  "etag": "act:crypto_mom_1h:abcd:long:42",
  "ts": "2025-08-28T09:00:00Z",
  "ack_ts": "2025-08-28T09:00:00Z",
  "idempotency_key": "activation_ack:crypto_mom_1h:7a1b4c...:17:unfreeze:1"
}
```

- `ActivationAck` is the acknowledgement message that Gateway publishes to the response channel (e.g., `control.activation.ack`) after it receives `ActivationUpdated.requires_ack=true`.
- The partition key is `world_id`; within a world, consumers should observe monotonic `sequence` ordering.
- Consumers deduplicate by `idempotency_key` or `(world_id, run_id, sequence, phase)`.

QueueUpdated (versioned)
```json
{
  "type": "QueueUpdated",
  "version": 1,
  "tags": ["BTC", "price"],
  "interval": 60,
  "queues": [
    {"queue": "q1", "global": false},
    {"queue": "q2", "global": true}
  ],
  "match_mode": "any",
  "etag": "q:BTC.price:60:1",
  "idempotency_key": "queue_updated:BTC.price:60:any:1",
  "ts": "2025-08-28T09:00:00Z"
}
```

SentinelWeightUpdated (versioned)
```json
{
  "type": "SentinelWeightUpdated",
  "version": 1,
  "sentinel_id": "s_123",
  "weight": 0.25,
  "sentinel_version": "v1.2.3",
  "world_id": "crypto_mom_1h",
  "etag": "sw:s_123:v1.2.3:0.250000:1",
  "ts": "2025-08-28T09:00:00Z",
  "idempotency_key": "sentinel_weight_updated:s_123:v1.2.3:0.250000:1"
}
```

PolicyUpdated (versioned)
```json
{
  "type": "PolicyUpdated",
  "version": 1,
  "world_id": "crypto_mom_1h",
  "policy_version": 3,
  "checksum": "blake3:...",
  "status": "ACTIVE",
  "ts": "2025-08-28T09:00:00Z"
}
```

---

## 3. Retention & QoS

- Retention: short (e.g., 1–24h) with compaction by key; enough for reconnection/replay
- QoS isolation: keep `control.*` topics separate from data topics; enforce quotas
- Rate limiting: backpressure to slow consumers; metrics exported for lag

---

## 3-A. Activation acknowledgement channel

- For each Freeze/Unfreeze event with `requires_ack=true`, Gateway publishes `ActivationAck` to the ControlBus response channel (e.g., `control.activation.ack`) only after the event is accepted in the contiguous sequence stream (SHALL). The payload MUST include `world_id`, `run_id`, and `sequence` so operators can reconcile state.
- If `requires_ack=true` but `sequence` is missing or not an integer, Gateway drops the message (increments `event_relay_dropped_total`) and publishes no ACK.
- For sequence gaps (`sequence > next_sequence`), current behavior is to buffer the message and defer both relay and ACK. Gateway does not currently run an in-consumer gap timeout or forced-resync routine; buffered gaps remain pending until the missing sequence arrives or the process restarts.
- Therefore timeout thresholds, alerting, and forced-resync actions (HTTP snapshot/state_hash reconcile, apply pause/rollback) are external WorldService/operations policy (SHOULD). In the current implementation, apply completion is not hard-blocked on ACK stream convergence. Baseline operational guidance is tracked in [ACK/Gap Resync RFC (Draft)](ack_resync_rfc.md).

---

## 4. Security

- Private to the cluster; no direct SDK access by default
- Service authentication (mTLS/JWT) for publishers/consumers
- Authorization by topic namespace and consumer group; tenant/world scoping enforced in consumer groups

---

## 5. Observability

Metrics
- Gateway (ControlBus consume/ACK): `controlbus_lag_ms`, `controlbus_apply_ack_total`, `controlbus_apply_ack_latency_ms`
- Gateway (WebSocket fan-out): `event_fanout_total`, `ws_dropped_subscribers_total`, `ws_connections_total`
- DAG Manager (queue lag): `queue_lag_seconds`, `queue_lag_threshold_seconds`

Runbooks
- Recreate consumer groups, increase partitions per world count, backfill via HTTP reconcile endpoints at Gateway/WorldService/DAG Manager

---

## 6. Integration Pattern

- WorldService publishes ActivationUpdated/PolicyUpdated.
- DAG Manager publishes QueueUpdated.
- Gateway instances subscribe to ControlBus and relay updates to SDK via an opaque WebSocket stream (`/events/subscribe`).

---

## 7. Initial Snapshot & Delegated WS (Optional)

- Initial snapshot: first message per topic SHOULD be a full snapshot or include a `state_hash` so clients can confirm convergence without a full GET.
- Clients MAY probe `/worlds/{world_id}/{topic}/state_hash` via Gateway to check for divergence before fetching a snapshot.
- Delegated WS (feature‑flagged): Gateway may return an alternate `alt_stream_url` that points to a dedicated event streamer tier sitting in front of ControlBus.
  - Tokens are short‑lived JWTs with claims: `aud=controlbus`, `sub=<user|svc>`, `world_id`, `strategy_id`, `topics`, `jti`, `iat`, `exp`. Key ID (`kid`) is conveyed in the JWT header.
  - Streamer verifies JWKS/claims and bridges to ControlBus; default deployment keeps this disabled.

{{ nav_links() }}
