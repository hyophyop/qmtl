---
title: "ControlBus — Internal Control Bus (Opaque to SDK)"
tags: [architecture, events, control]
author: "QMTL Team"
last_modified: 2025-11-12
---

{{ nav_links() }}

# ControlBus — Internal Control Bus

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

---

## 1. Topology & Semantics

- Transport: Kafka/Redpanda recommended, or equivalent pub/sub; namespaces `control.*`
- Topics (example)
  - `control.activation` partitioned by `world_id`
  - `control.queues` partitioned by `hash(tags, interval)`
  - `control.policy` partitioned by `world_id`
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
- `requires_ack=true` indicates Gateway MUST confirm receipt via the ControlBus acknowledgement channel before reopening order flow. Until that acknowledgement lands, Gateway/SDK keep order gates closed.
- `sequence` is the per-run monotonic counter produced by [`ApplyRunState.next_sequence()`]({{ code_url('qmtl/services/worldservice/run_state.py#L47') }}). Consumers enforce increasing order and trigger resync when gaps are detected.

QueueUpdated (versioned)
```json
{
  "type": "QueueUpdated",
  "version": 1,
  "tags": ["BTC", "price"],
  "interval": 60,
  "queues": ["q1", "q2"],
  "etag": "q:BTC.price:60:77",
  "ts": "2025-08-28T09:00:00Z"
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

- For every Freeze/Unfreeze event, Gateway publishes an acknowledgement containing the latest `sequence` to ControlBus (e.g., `control.activation.ack`) or an equivalent response channel (SHALL). The payload MUST include `world_id`, `run_id`, and `sequence` so operators can reconcile state.
- WorldService and operational tooling SHOULD monitor the acknowledgement stream for missing sequences or timeouts and pause/rollback apply runs when anomalies surface.
- Gateway SHOULD delay sending ControlBus acknowledgements if downstream SDK/WebSocket clients have not acknowledged receipt, keeping freeze semantics intact.

---

## 4. Security

- Private to the cluster; no direct SDK access by default
- Service authentication (mTLS/JWT) for publishers/consumers
- Authorization by topic namespace and consumer group; tenant/world scoping enforced in consumer groups

---

## 5. Observability

Metrics
- controlbus_publish_latency_ms, fanout_lag_ms, dropped_subscribers_total
- replay_queue_depth, partition_skew_seconds

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
- Clients MAY probe `/worlds/{id}/{topic}/state_hash` via Gateway to check for divergence before fetching a snapshot.
- Delegated WS (feature‑flagged): Gateway may return an alternate `alt_stream_url` that points to a dedicated event streamer tier sitting in front of ControlBus.
  - Tokens are short‑lived JWTs with claims: `aud=controlbus`, `sub=<user|svc>`, `world_id`, `strategy_id`, `topics`, `jti`, `iat`, `exp`. Key ID (`kid`) is conveyed in the JWT header.
  - Streamer verifies JWKS/claims and bridges to ControlBus; default deployment keeps this disabled.

{{ nav_links() }}
