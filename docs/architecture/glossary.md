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
- ControlBus: Internal control bus (Kafka/Redpanda) carrying versioned control events (ActivationUpdated, QueueUpdated, PolicyUpdated); not a public API.
- EventStreamDescriptor: Opaque WS descriptor from Gateway (`stream_url`, `token`, `topics`, `expires_at`, optional `fallback_url`, `alt_stream_url`).
- etag: Monotonic version identifier used for deduplication and concurrent update checks.
- run_id: Idempotency token for 2‑phase apply operations.
- TTL: Time‑to‑Live; cache validity horizon for DecisionEnvelope.
- data_currency: Freshness policy comparing `now` and `data_end` to choose initial mode.
- state_hash: Optional hash of an activation set snapshot, used to detect divergence cheaply.

- Global Strategy Graph (GSG): Content‑addressed, deduplicated global DAG of strategies and nodes; immutable/append‑only SSOT owned by DAG Manager.
- World View Graph (WVG): Per‑world overlay referencing GSG nodes with world‑local metadata (status, validation, decisions); mutable SSOT owned by WorldService.
- NodeID: Deterministic BLAKE3 hash of a node’s canonical form: `(node_type, interval, period, params(canonical, split), dependencies(sorted), schema_compat_id, code_hash)`. `schema_compat_id` is the Schema Registry’s major‑compat identifier; minor/patch compatible changes keep the same `schema_compat_id` and thus preserve `node_id`.
- schema_compat_id: Major‑compatibility identifier used in NodeID canonicalization. Distinct from `schema_id`.
- schema_id: Concrete schema registry identifier for lookup/resolution; may change across minor/patch versions without affecting `schema_compat_id`.
- EvalKey: BLAKE3 hash for world‑local validation cache: `(NodeID, WorldID, ContractID, DatasetFingerprint, CodeVersion, ResourcePolicy)`.
- WorldNodeRef: `(world_id, node_id)` scoped record storing world‑local status, `last_eval_key`, and annotations.
- DecisionEvent: Operational action (`stop|pause|resume|quarantine`) for a `node_id` (strategy root allowed); default `scope=world-local`, optional propagation with TTL.
- SSOT boundary: DAG Manager owns GSG only; WorldService owns WVG only. Gateway proxies/caches; it is not an SSOT.

{{ nav_links() }}
