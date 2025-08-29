---
title: "Architecture Glossary"
tags: [architecture, glossary]
author: "QMTL Team"
last_modified: 2025-08-29
---

{{ nav_links() }}

# Architecture Glossary

- DecisionEnvelope: World decision result containing `world_id`, `policy_version`, `effective_mode`, `reason`, `as_of`, `ttl`, `etag`.
- ActivationEnvelope: Activation state for a `(world_id, strategy_id, side)` with `active`, `weight`, `etag`, `run_id`, `ts` and optional `state_hash`.
- EventPool: Internal control bus (Kafka/Redpanda) carrying versioned control events (ActivationUpdated, QueueUpdated, PolicyUpdated); not a public API.
- EventStreamDescriptor: Opaque WS descriptor from Gateway (`stream_url`, `token`, `topics`, `expires_at`, optional `fallback_url`, `alt_stream_url`).
- etag: Monotonic version identifier used for deduplication and concurrent update checks.
- run_id: Idempotency token for 2‑phase apply operations.
- TTL: Time‑to‑Live; cache validity horizon for DecisionEnvelope.
- data_currency: Freshness policy comparing `now` and `data_end` to choose initial mode.
- state_hash: Optional hash of an activation set snapshot, used to detect divergence cheaply.

{{ nav_links() }}

