---
title: "Architecture Glossary"
tags: [architecture, glossary]
author: "QMTL Team"
last_modified: 2025-11-22
---

{{ nav_links() }}

# Architecture Glossary

- DecisionEnvelope: World decision result containing `world_id`, `policy_version`, `effective_mode`, `reason`, `as_of`, `ttl`, `etag`.
- effective_mode: Policy output string in DecisionEnvelope. Values: `validate | compute-only | paper | live`. Consumers MUST map to an ExecutionDomain for compute/routing; see mapping below.
- execution_domain: Derived field emitted by Gateway/SDK after mapping `effective_mode` (`backtest | dryrun | live | shadow`). Persisted on envelopes relayed to SDKs. Caller-supplied `meta.execution_domain` is only a hint; the authoritative value derives from WS `effective_mode`. Runner/SDK retain `shadow` (no backtest downgrade) while hard-blocking order publish.
- ActivationEnvelope: Activation state for a `(world_id, strategy_id, side)` with `active`, `weight`, `etag`, `run_id`, `ts` and optional `state_hash`.
- ControlBus: Internal control bus (Kafka/Redpanda) carrying versioned control events (ActivationUpdated, QueueUpdated, PolicyUpdated); not a public API.
- EventStreamDescriptor: Opaque WS descriptor from Gateway (`stream_url`, `token`, `topics`, `expires_at`, optional `fallback_url`, `alt_stream_url`).
- etag: Monotonic version identifier used for deduplication and concurrent update checks.
- run_id: Idempotency token for 2-phase apply operations.
- TTL: Time-to-Live; cache validity horizon for DecisionEnvelope.
- data_currency: Freshness policy comparing `now` and `data_end` to choose initial mode.
- state_hash: Optional hash of an activation set snapshot, used to detect divergence cheaply.

- Global Strategy Graph (GSG): Content-addressed, deduplicated global DAG of strategies and nodes; immutable/append-only SSOT owned by DAG Manager.
- World View Graph (WVG): Per-world overlay referencing GSG nodes with world-local metadata (status, validation, decisions); mutable SSOT owned by WorldService.
- NodeID: Deterministic BLAKE3 hash of a node's canonical form: `(node_type, interval, period, params(canonical, split), dependencies(sorted), schema_compat_id, code_hash)`. `schema_compat_id` is the Schema Registry's major-compat identifier; minor/patch compatible changes keep the same `schema_compat_id` and thus preserve `node_id`.
- schema_compat_id: Major-compatibility identifier used in NodeID canonicalization. Distinct from `schema_id`.
- schema_id: Concrete schema registry identifier for lookup/resolution; may change across minor/patch versions without affecting `schema_compat_id`.
- EvalKey: BLAKE3 hash for world-local validation cache: `(NodeID || WorldID || ExecutionDomain || ContractID || DatasetFingerprint || CodeVersion || ResourcePolicy)`; domain-scopes validation so backtest/live caches never mix.
- WorldNodeRef: `(world_id, node_id, execution_domain)` scoped record storing world- and domain-local `status`, `last_eval_key`, and annotations.
- DecisionsRequest: API payload replacing the per-world strategy set; contains an ordered list of unique, non-empty strategy identifiers persisted by WorldService.
- SSOT boundary: DAG Manager owns GSG only; WorldService owns WVG only. Gateway proxies/caches; it is not an SSOT.

## Execution Domain & Isolation

- ExecutionDomain: Compute/run context of a world. One of `backtest | dryrun | live | shadow`. Drives gating, queue routing, and validation scope.
- Domain-Scoped ComputeKey: Internal dedup/cache key used by DAG Manager and runtimes: `ComputeKey = blake3(NodeHash + world_id + execution_domain + as_of + partition)`. NodeID remains world-agnostic; ComputeKey enforces cross-domain/world isolation.
- EdgeOverride (WVG scope): World-local reachability control per edge; used to disable cross-domain paths (e.g., backtest graph -> live queues) until policy-driven enablement. Implemented by [`EdgeOverrideRepository`]({{ code_url('qmtl/services/worldservice/storage/edge_overrides.py#L13') }}) and surfaced via the WorldService [`/worlds/{world_id}/edges/overrides`]({{ code_url('qmtl/services/worldservice/routers/worlds.py#L109') }}) API.
- 2-Phase Apply: WorldService operation ensuring safe domain switches: `Freeze/Drain -> Switch(domain) -> Unfreeze`. Orders are gated OFF while `freeze=true`.
- Feature Artifact: Immutable output of the Feature Plane identified by `(factor, interval, params, instrument, t, dataset_fingerprint)`. Shared read-only across ExecutionDomains.
- dataset_fingerprint: Token representing the data snapshot used for validation/promotion; policies and EvalKey MUST include it.
- share_policy: Policy flag controlling how artifacts are reused. `feature-artifacts-only` forbids runtime cache sharing and mandates read-only artifact consumption.
- cross_context_cache_hit_total: Counter emitted by SDK/DAG Manager when a cache hit occurs with mismatched `(world_id, execution_domain, as_of, partition)`; MUST stay at 0.

Execution mode -> ExecutionDomain mapping (normative)
- `validate` -> same as `compute-only` with orders gated OFF; defaults to `backtest` unless operators request `shadow` explicitly
- `compute-only` -> `backtest`
- `paper` / `sim` -> `dryrun`
- `live` -> `live`
- `offline`/`sandbox` and other ambiguous aliases -> `backtest`

<a id="shadow-execution-domain"></a>
### Shadow execution_domain parallel agreement
- Shared contract: `shadow` is a live-input mirror with orders hard-blocked and its namespace isolated. Caller `meta.execution_domain=shadow` is only a hint; the authoritative value comes from WS `effective_mode`.
- Field/tag/error consistency: Keep `execution_domain=shadow` across all Runner/SDK/Gateway/WS paths and apply the same label to ComputeKey/EvalKey/caches (including arrow), ControlBus/WebSocket relays, metrics/history/tag queries. Order publish paths must ignore or explicitly reject shadow.
- Test ownership split: Runner/SDK validate queue/node execution, no order publish, and cache keys containing shadow on shadow submissions. Gateway/WS cover submission/context passthrough, relay tagging, tag-query/queue-map tests, and operator doc updates.
- Merge/interop: Shadow workstreams on Runner/SDK and Gateway/WS can land in parallel; once both are in, run an end-to-end shadow path check.

Auxiliary terms
- as_of: Dataset snapshot timestamp or commit identifier that binds backtests to a fixed input view for deterministic replay.
- partition: Optional tenant/portfolio/strategy partitioning key included in ComputeKey to scope multi-tenant execution.
- NodeHash: Canonical hash input used to derive NodeID (blake3 digest of the canonical node form).
- WSB (WorldStrategyBinding): `(world_id, strategy_id)` association created by Gateway on submission to ensure the root `WorldNodeRef` exists.

{{ nav_links() }}
