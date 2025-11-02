---
title: "WorldService - World Policy, Decisions, and Activation"
tags: [architecture, world, policy]
author: "QMTL Team"
last_modified: 2025-09-22
---

{{ nav_links() }}

# WorldService - World Policy, Decisions, and Activation

## 0. Role & Scope

WorldService is the system of record (SSOT) for Worlds. It owns:
- World/Policy registry: CRUD, versioning, defaults, rollback
- Decision engine: data-currency, sample sufficiency, gates/score/constraints, hysteresis -> effective_mode (policy string). Gateway derives the downstream execution_domain from this mode when relaying decisions/activations.
- Activation control: per-world activation set for strategies/sides with weights
- ExecutionDomain as a first-class concept: `backtest | dryrun | live | shadow` per world
- 2-Phase apply: Freeze/Drain -> Switch -> Unfreeze, idempotent with run_id
- Audit & RBAC: every policy/update/decision/apply event is logged and authorized
- Events: emits activation/policy updates to the internal ControlBus

!!! note "Design intent"
- WS produces `effective_mode` (policy string); Gateway maps it to `execution_domain` and propagates via a shared compute context. SDK/Runner do not choose modes and treat the mapped domain as input only. Stale/unknown decisions default to compute-only with order gates OFF.

Non-goals: Strategy ingest, DAG diff, queue/tag discovery (owned by Gateway/DAG Manager). Order I/O is not handled here.

---

## 1. Data Model (normative)

Worlds (DB)
- world_id (pk, slug), name, description, owner, labels[]
- created_at, updated_at, state (ACTIVE|SUSPENDED|DELETED)
- default_policy_version, allow_live (bool), circuit_breaker (bool)

WorldPolicies (DB)
- (world_id, version) (pk), yaml (text), checksum, status (DRAFT|ACTIVE|DEPRECATED)
- created_by, created_at, valid_from (optional)

WorldActivation (Redis)
- Key: world:<id>:active -> { strategy_id|side : { active, weight, etag, run_id, ts } }
- Snapshots periodically persisted to DB for audit

WorldAuditLog (DB)
- id, world_id, actor, event (create/update/apply/evaluate/activate/override)
- request, result, created_at, correlation_id

Implementation note: the reference service now ships with a persistent backend
(`qmtl.services.worldservice.storage.PersistentStorage`) that stores these relational
surfaces in SQL (SQLite or Postgres) and activation state in Redis. Production
deployments wire this backend by default, while unit tests can continue using
the in-memory facade for lightweight fixtures. All APIs described below operate
against this durable adapter.

### 1-A. WVG Data Model (normative)

WorldService is the SSOT for the World View Graph (WVG), a per-world overlay referencing global GSG nodes (Global Strategy Graph=GSG):

- WorldNodeRef (DB): `(world_id, node_id, execution_domain)` -> `status` (`unknown|validating|valid|invalid|running|paused|stopped|archived`), `last_eval_key`, `annotations{}`
- Validation (DB): `eval_key = blake3:(NodeID||WorldID||ContractID||DatasetFingerprint||CodeVersion||ResourcePolicy)` (**'blake3:' prefix required**), `result`, `metrics{}`, `timestamp`
- DecisionsRequest (DB/API): `strategies` (ordered, deduplicated list of strategy identifiers) stored per-world via `/worlds/{world_id}/decisions`
- **EdgeOverride (DB, WVG scope):** World-local reachability control record.  
  Shape: `(world_id, src_node_id, dst_node_id, active=false, reason)`, identifying edges that must be disabled for a specific world.  
  Implementation: [`EdgeOverrideRepository`]({{ code_url('qmtl/services/worldservice/storage/edge_overrides.py#L13') }}) persists the objects and the WorldService route [`/worlds/{world_id}/edges/overrides`]({{ code_url('qmtl/services/worldservice/routers/worlds.py#L109') }}) exposes CRUD.

SSOT boundary: WVG objects are not stored by DAG Manager. WS owns their lifecycle and emits changes via ControlBus.

---

## 2. API Surface (summary)

CRUD
- POST /worlds | GET /worlds | GET /worlds/{id} | PUT /worlds/{id} | DELETE /worlds/{id}

Policies
- POST /worlds/{id}/policies  (upload new version)
- GET /worlds/{id}/policies   (list) | GET /worlds/{id}/policies/{v}
- POST /worlds/{id}/set-default?v=V

Bindings
- POST /worlds/{id}/bindings        (upsert WSB: bind `strategy_id` to world)
- GET  /worlds/{id}/bindings        (list; filter by `strategy_id`)

Purpose
- WSB ensures a `(world_id, strategy_id)` root exists in the WVG for each submission. For operational isolation and resource control, running separate processes per world is recommended when strategies target multiple worlds.

Decisions & Control
- GET /worlds/{id}/decide?as_of=... -> DecisionEnvelope
- POST /worlds/{id}/decisions       (replace world strategy set via DecisionsRequest)
- GET /worlds/{id}/activation?strategy_id=...&side=... -> ActivationEnvelope
- PUT /worlds/{id}/activation          (manual override; optional TTL)
- POST /worlds/{id}/evaluate           (plan only)
- POST /worlds/{id}/apply              (2-Phase apply; requires run_id)
- GET /worlds/{id}/audit               (paginated stream)

RBAC: world-scope roles (owner, reader, operator). Sensitive ops (`apply`, `activation PUT`) require operator.

---

## 3. Envelopes (normative)

The canonical Pydantic models for these envelopes live in [`qmtl/services/worldservice/schemas.py`]({{ code_url('qmtl/services/worldservice/schemas.py') }}). ControlBus fan-out (e.g., `ActivationUpdated`) reuses these payloads; see [`docs/reference/schemas/event_activation_updated.schema.json`](../reference/schemas/event_activation_updated.schema.json) for the CloudEvent wrapper.

DecisionEnvelope
```json
{
  "world_id": "crypto_mom_1h",
  "policy_version": 3,
  "effective_mode": "validate",  
  "reason": "data_currency_ok&gates_pass&hysteresis",
  "as_of": "2025-08-28T09:00:00Z",
  "ttl": "300s",
  "etag": "w:crypto_mom_1h:v3:1724835600"
}
```

`effective_mode` remains the legacy policy string. Gateway/SDK derive an
ExecutionDomain from it and only attach `execution_domain` on the
ControlBus/WebSocket copies they relay downstream; the field is not part of
the canonical WorldService schema.

ActivationEnvelope
```json
{
  "world_id": "crypto_mom_1h",
  "strategy_id": "abcd",
  "side": "long",
  "active": true,
  "weight": 1.0,
  "freeze": false,
  "drain": false,
  "effective_mode": "paper",
  "etag": "act:crypto_mom_1h:abcd:long:42",
  "run_id": "7a1b4c...",
  "ts": "2025-08-28T09:00:00Z"
}
```

Field semantics and precedence
- `freeze=true` overrides `drain`; both imply orders gated OFF.
- `drain=true` blocks new orders but allows existing opens to complete naturally.
- When either `freeze` or `drain` is true, `active` is effectively false (explicit flags provided for clarity and auditability).
- `weight` soft-scales sizing in the range [0.0, 1.0]. If absent, default is 1.0 when `active=true`, else 0.0.
- `effective_mode` communicates the legacy policy string from WorldService (`validate|compute-only|paper|live`).
- Gateway derives an `execution_domain` when relaying the envelope downstream (ControlBus -> SDK) by mapping `effective_mode` as `validate -> backtest (orders gated OFF by default)`, `compute-only -> backtest`, `paper -> dryrun`, `live -> live`. `shadow` remains reserved for operator-led validation streams. The canonical ActivationEnvelope schema emitted by WorldService omits this derived field; Gateway adds it for clients so the mapping stays centralized.

Idempotency: consumers must treat older etag/run_id as no-ops. Unknown or expired decisions/activations should default to "inactive/safe".

TTL & Staleness
- DecisionEnvelope includes a TTL (default 300s if unspecified). After TTL, Gateway must treat the decision as stale and enforce a safe default: compute-only (orders gated OFF) until a fresh decision is obtained.
- Activation has no TTL but carries `etag` (and optional `state_hash`). Unknown/expired activation -> orders gated OFF.

---

### 4. Execution Domains & Apply (normative)

- Domains: `backtest | dryrun | live | shadow`.
- Isolation invariants:
  - Cross-domain edges MUST be disabled by default via `EdgeOverride` until a policy explicitly enables them post-promotion.
  - Orders are always gated OFF while `freeze=true` during 2-Phase apply.
  - Domain switch is atomic from the perspective of order gating: `Freeze/Drain -> Switch(domain) -> Unfreeze`.
- 2-Phase Apply protocol (SHALL):
  1. **Freeze/Drain** - Activation entries set `active=false, freeze=true`; Gateway/SDK gate all order publications; EdgeOverride keeps live queues disconnected.
  2. **Switch** - ExecutionDomain updated (e.g., `backtest -> live`), queue/topic bindings refreshed, Feature Artifact snapshot pinned via `dataset_fingerprint`.
  3. **Unfreeze** - Activation resumes (`freeze=false`) only after Gateway/SDK acknowledge the ActivationUpdated event for the new domain.
  - Single-flight guard: Only one apply may execute per world at a time (SHALL). Additional requests return 409 or are queued.
  - Failure policy: If the Switch step fails, immediately roll back to the previous Activation snapshot and remain frozen (SHALL).
  - Audit: Record the timeline `requested -> freeze -> switch -> unfreeze -> completed/rolled_back` in WorldAuditLog (SHOULD).
- Queue namespace guidance: In production, enforce `{world_id}.{execution_domain}.<topic>` namespaces and ACLs to prevent cross-domain access (SHALL). NodeID/topic conventions remain unchanged.
- Dataset Fingerprint: Promotions MUST pin to a specific data snapshot (`dataset_fingerprint`) so EvalKey separates cross-domain revalidation (SHALL).

---

## 4. Decision Semantics

- Data Currency: now - data_end <= max_lag -> near-real-time; else compute-only replay until caught up (orders remain gated OFF)
- Sample Sufficiency: metric-specific minimums (days, trades, bars) gate before scoring
- Gates: AND/OR of thresholds; Score: weighted function; Constraints: correlation/exposure
- Hysteresis: promote_after, demote_after, min_dwell to avoid flapping

The evaluation returns DecisionEnvelope and an optional plan for apply.

### 4-A. DecisionsRequest Updates (WVG)

- `/worlds/{world_id}/decisions` accepts a `DecisionsRequest` and replaces the stored strategy list atomically for that world (MUST).
- Entries are validated as non-empty strings, deduplicated, and preserved in request order before being persisted (SHALL).
- Clearing the list removes all active strategies for the world; subsequent `/decide` calls return `validate` mode until strategies are restored (SHOULD).

### 4-B. EvalKey and Validation Caching

- EvalKey = `blake3(NodeID || WorldID || ExecutionDomain || ContractID || DatasetFingerprint || CodeVersion || ResourcePolicy)`
- ExecutionDomain is normalised (case-insensitive) before hashing and storage so cache keys remain domain-scoped and comparable.
- Any change in the components invalidates cache and triggers re-validation. Invalidation removes the scoped domain entry (and empties the node/world bucket when last entry is purged) to prevent stale re-use.

### 4-C. Gating Policy Specification (normative)

Reference YAML structure enforced by policy tooling:

```yaml
gating_policy:
  promotion_point: "2025-10-01T00:00:00Z"
  apply: { mode: two_phase, freeze_timeout_ms: 30000 }
  domains: { from: backtest, to: live }
  clocks:
    backtest: { type: virtual, epoch0: "2020-01-01T00:00:00Z" }
    live:     { type: wall }
  dataset_fingerprint: "ohlcv:ASOF=2025-09-30T23:59:59Z"
  share_policy: "feature-artifacts-only"   # runtime cache sharing forbidden
  snapshot:
    strategy_plane: "cow"
    feature_plane: "readonly"
  risk_limits:
    max_pos_usd_long:  500000
    max_pos_usd_short: 500000
  divergence_guards:
    feature_drift_bp_long: 5
    feature_drift_bp_short: 5
    slippage_bp_long: 10
    slippage_bp_short: 12
  execution_model:
    fill: "bar-mid+slippage"
    fee_bp: 2
  can_short: true
  edges:
    pre_promotion:  { disable_edges_to: "live" }
    post_promotion: { enable_edges_to:  "live" }
  observability:
    slo: { cross_context_cache_hit: 0 }
    audit_topic: "gating.alerts"
```

- Policies MUST specify `dataset_fingerprint`, an explicit `share_policy`, and edge overrides for pre/post promotion. Missing elements downgrade the Apply to compute-only or reject it outright.
- `observability.slo.cross_context_cache_hit` SHALL remain 0; violations block execution. Gateway/SDK monitor the metric and ControlBus events to enforce the SLO.
- The `snapshot`/`share_policy` combination must comply with the Feature Artifact Plane rules (Sec.1.4). Strategy Plane uses copy-on-write, whereas the Feature Plane is shared only as read-only replicas.
- `risk_limits`, `divergence_guards`, and the `execution_model` are evaluated during pre-promotion validation. Failures reject the Apply and leave the world frozen.

---

## 5. Security & RBAC

- Auth: service-to-service tokens (mTLS/JWT); user tokens at Gateway -> propagated to WS
- World-scope RBAC enforced at WS; Gateway only proxies
- Audit: all write ops and evaluations are logged with correlation_id

Clock Discipline
- Decisions depend on time. WS uses a monotonic server clock and enforces NTP health. Maximum tolerated client skew should be documented (e.g., <= 2s).

---

## 6. Observability & SLOs

Metrics example
- world_decide_latency_ms_p95, world_apply_duration_ms_p95
- activation_skew_seconds, promotion_fail_total, demotion_fail_total
- registry_write_fail_total, audit_backlog_depth
- cross_context_cache_hit_total (target=0; violation blocks promotions)

Skew Metrics
- `activation_skew_seconds` is measured as the difference between the event `ts` and the time the SDK processes it, aggregated p95 per world.

Alerts
- Decision failures, explicit status polling failures, stale activation cache at Gateway
- cross_context_cache_hit_total > 0 (CRIT): investigate domain mixing before re-enabling apply

---

## 7. Failure Modes & Recovery

- WS down: Gateway returns cached DecisionEnvelope if fresh; else safe default (compute-only/inactive). Activation defaults to inactive.
- Redis loss: reconstruct activation from latest snapshot; orders remain gated until consistency restored.
- Policy parse errors: reject version; keep prior default.

---

## 8. Integration & Events

- Gateway: proxy `/worlds/*`, cache decisions with TTL, enforce `--allow-live` guard
- DAG Manager: no dependency for decisions; only for queue/graph metadata
- ControlBus: WS publishes ActivationUpdated/PolicyUpdated; Gateway subscribes and relays via WS to SDK

Runner & SDK Integration (clarification)
- SDK/Runner do not expose execution modes. Callers provide only `world_id` when starting a strategy; Runner adheres to WorldService decisions and activation events.
- `effective_mode` in DecisionEnvelope is computed by WS and treated as input by SDK. Unknown or stale decisions default to compute-only with order gates OFF.
- On submission the Gateway guarantees a **WSB upsert** for each `world_id`, creating or updating a `WorldNodeRef(root)` entry in the WVG.

---

## 9. Testing & Validation

- Contract tests for envelopes (Decision/Activation) using the JSON Schemas (reference/schemas.md).
- Idempotency tests: duplicate/out-of-order event handling based on `etag`/`run_id`.
- WS reconcile tests: initial snapshot vs. `state_hash` divergence handling and HTTP fallback.

{{ nav_links() }}
