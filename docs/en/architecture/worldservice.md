---
title: "WorldService - World Policy, Decisions, and Activation"
tags: [architecture, world, policy]
author: "QMTL Team"
last_modified: 2026-02-06
spec_version: v1.0
---

{{ nav_links() }}

# WorldService - World Policy, Decisions, and Activation

Related: [Core Loop × WorldService — Campaign Automation and Promotion Governance](core_loop_world_automation.md)  
Related: [ACK/Gap Resync RFC (Draft)](ack_resync_rfc.md)

## 0. Role & Scope

WorldService is the system of record (SSOT) for Worlds. It owns:
- World/Policy registry: CRUD, versioning, defaults, rollback
- Decision engine: data-currency, sample sufficiency, gates/score/constraints, hysteresis -> effective_mode (policy string). Gateway derives the downstream execution_domain from this mode when relaying decisions/activations.
- Activation control: per-world activation set for strategies/sides with weights
- ExecutionDomain as a first-class concept: `backtest | dryrun | live | shadow` per world
- 2-Phase apply: Freeze/Drain -> Switch -> Unfreeze, idempotent with run_id
- Audit & RBAC: every policy/update/decision/apply event is logged and authorized
- Events: emits activation/policy updates to the internal ControlBus

!!! note "Deployment profile"
    With `profile: dev`, WorldService uses an in-memory activation store when Redis is not configured. With `profile: prod`, missing `worldservice.server.redis` fails fast before startup; in-memory mode is not allowed.

!!! note "Risk Signal Hub integration"
    - WorldService receives and stores portfolio/risk snapshots via the `/risk-hub/*` router, and the ExtendedValidation/stress/live workers perform VaR/ES and stress calculations via hub queries/events.
    - Dev profile: uses only in-memory/SQLite + fakeredis cache; covariance and similar artifacts are inline (ref offload disabled).
    - Prod profile: uses Postgres `risk_snapshots` + Redis cache, and can enable S3/Redis blob offload via hub settings when needed.
    - Gateway only pushes snapshots to the hub; the hub consumers are WorldService (and the exit engine).

!!! warning "Default-safe"
- Do not default to live when inputs are missing or ambiguous; downgrade to compute-only (backtest) if `execution_domain` is empty or omitted. WS API calls must not persist live by default.
- With `allow_live=false` (default), activation/domain switches must not move to live even if operators request it. Only promote when policy validation passes (required signals, hysteresis, dataset_fingerprint anchored).
- When clients omit `execution_domain`, world nodes and validation caches are stored under `backtest` by default. Explicitly set the intended domain in API payloads to avoid accidental live scope.

!!! note "Policy engine implementation status"
    The current `/worlds/{world_id}/decide` endpoint decides `effective_mode` and TTL/reasons only based on the world’s `allow_live` flag, the presence of bindings/decisions, and history metadata (dataset_fingerprint, coverage, etc.). The finer-grained scoring/hysteresis/required signal sets (StrategySeries-based) and domain-specific edge override integrations described in the policy docs are not implemented yet. When the WorldService policy engine is ready, we will integrate that evaluation logic and SSOT into this path.

!!! note "Design intent"
- WS produces `effective_mode` (policy string); Gateway maps it to `execution_domain` and propagates via a shared compute context. SDK/Runner do not choose modes and treat the mapped domain as input only. Stale/unknown decisions default to compute-only with order gates OFF.
- Submission `meta.execution_domain` values are treated only as hints; the authoritative domain always derives from the WS `effective_mode`.

QMTL’s core value — **“focus only on strategy logic; the system handles optimisation and returns”** — is realised in WorldService as follows:
- Strategy authors only submit strategies to worlds; **validation, promotion/demotion, weight adjustments, and risk constraints** are enforced automatically by WS policies.
- From a world-portfolio perspective, only strategies that are classified as `valid` are admitted so that **world-level risk-adjusted returns do not degrade**, aiming as closely as possible at monotonic improvement.
- SDK/Runner and Gateway act purely as consumers of WS decision envelopes; user interfaces do not require operators to understand or control ExecutionDomain details or the apply protocol to benefit from world decisions.
- When evolving policies/schemas, avoid keeping old and new fields or modes indefinitely for compatibility; after a defined migration window, converge on a single “current” policy model (prioritising simplicity over backward compatibility).

Non-goals:
- Strategy ingest, DAG diff, queue/tag discovery (owned by Gateway/DAG Manager). Order I/O is not handled here.
- Supporting a full strategy lifecycle and final evaluation/gating in a **“pure local, SDK-only” mode** (without WorldService/Gateway) as an official operating mode. SDK-level ValidationPipeline/PnL helpers exist for tests and experiments, but WorldService remains the SSOT for policies, evaluation, and gating.

### 0-A. Core Loop Alignment

Related: [Core Loop × WorldService — Campaign Automation and Promotion Governance](core_loop_world_automation.md)

#### Evaluation & Activation Flow

- WS evaluation results (active/weight/contribution/violations) are the **single world-level source of truth**, surfaced directly by SDK/Runner; `ValidationPipeline` stays as a hint/local pre-check only.
- `DecisionEnvelope`/`ActivationEnvelope` schemas and Runner/CLI `SubmitResult` are aligned so “submit strategy → inspect world decision” reads as a single flow.
- Contract (aligned)
  - `/worlds/{world_id}/evaluate` produces `DecisionEnvelope`/`ActivationEnvelope` that map directly to `SubmitResult.ws.decision/activation`; CLI `--output json` emits the same WS/Precheck-separated structure.
  - Local `ValidationPipeline` output lives only in `SubmitResult.precheck`; `status/weight/rank/contribution` SSOT is always WS.
  - `ActivationEnvelope` (`GET/PUT /worlds/{world_id}/activation`) shares the same schema as `SubmitResult.ws.activation`, exposing `active/weight/etag/run_id`. `state_hash` is exposed via `/worlds/{world_id}/activation/state_hash` and ActivationUpdated events.

#### ExecutionDomain / effective_mode

- The current `/worlds/{world_id}/decide` policy path emits `effective_mode` in `validate | compute-only | live`. Gateway/SDK map `effective_mode` to `execution_domain(backtest/dryrun/live/shadow)`, and the mapper also accepts `paper`/`shadow` tokens for activation/manual-override payloads.
- Submission `meta.execution_domain` is advisory at most; authority sits with WS `effective_mode`, and the mapping/precedence rules are shared across `world/world.md`, `architecture.md`, `gateway.md`, and this document.

#### World-Level Allocation / Rebalancing

- `/allocations`, `/rebalancing/plan`, and `/rebalancing/apply` compute and record world and cross-world allocation plans; Runner.submit/CLI surface the latest snapshot (world/strategy totals, etag/updated_at, staleness) for the submitted world as read-only context and hint users to refresh with `qmtl world allocations -w <id>` when missing or stale.
- The submission/evaluation loop and the world allocation loop are a **standard two-step flow** with WS as SSOT for evaluation/activation/allocation and apply/rebalancing remaining an auditable, operator-led step (`qmtl world apply <id> --run-id <id> [--plan-file ...]`) anchored by run_id/etag tracking.

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
- Key: world:<id>:activation -> { strategy_id|side : { active, weight, etag, run_id, ts } }
- Activation state is stored in Redis; activation mutations are recorded in `WorldAuditLog` entries for audit/recovery.

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
- POST /worlds | GET /worlds | GET /worlds/{world_id} | PUT /worlds/{world_id} | DELETE /worlds/{world_id}

Policies
- POST /worlds/{world_id}/policies  (upload new version)
- GET /worlds/{world_id}/policies   (list) | GET /worlds/{world_id}/policies/{v}
- POST /worlds/{world_id}/set-default?v=V

Bindings
- POST /worlds/{world_id}/bindings        (upsert WSB: bind `strategy_id` to world)
- GET  /worlds/{world_id}/bindings        (list; filter by `strategy_id`)

Purpose
- WSB ensures a `(world_id, strategy_id)` root exists in the WVG for each submission. For operational isolation and resource control, running separate processes per world is recommended when strategies target multiple worlds.

Decisions & Control
- GET /worlds/{world_id}/decide?as_of=... -> DecisionEnvelope
- POST /worlds/{world_id}/decisions       (replace world strategy set via DecisionsRequest)
- GET /worlds/{world_id}/activation?strategy_id=...&side=... -> ActivationEnvelope
- GET /worlds/{world_id}/activation/state_hash -> activation state hash metadata
- PUT /worlds/{world_id}/activation          (manual override; no TTL field in request)
- POST /worlds/{world_id}/evaluate           (plan only)
- POST /worlds/{world_id}/apply              (2-Phase apply; requires run_id)
- GET /worlds/{world_id}/audit               (paginated stream)

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

`effective_mode` remains the policy string.
`execution_domain`/`compute_context` are Gateway augmentation fields, not part
of the canonical WorldService schema. Gateway materializes them on HTTP proxy
responses (`GET /worlds/{id}/decide`, `GET /worlds/{id}/activation`), on
activation bootstrap frames emitted by `/events/subscribe`, and on
ControlBus `activation_updated` relays.

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
  "ts": "2025-08-28T09:00:00Z",
  "phase": "unfreeze",
  "requires_ack": true,
  "sequence": 17
}
```

Field semantics and precedence
- `freeze=true` overrides `drain`; both imply orders gated OFF.
- `drain=true` blocks new orders but allows existing opens to complete naturally.
- When either `freeze` or `drain` is true, `active` is effectively false (explicit flags provided for clarity and auditability).
- `weight` soft-scales sizing in the range [0.0, 1.0]. If omitted in a WS activation write, storage currently persists `1.0` regardless of `active`; downstream order gating still treats inactive/frozen/draining states as non-tradable.
- `effective_mode` communicates the policy string from WorldService (`validate|compute-only|paper|live|shadow`).
- Gateway augmentation paths (`GET /worlds/{id}/activation`, activation bootstrap over `/events/subscribe`, ControlBus `activation_updated` relay): map `effective_mode` as `validate -> backtest`, `compute-only -> backtest`, `paper -> dryrun`, `live -> live`, `shadow -> shadow`, then materialize `execution_domain`/`compute_context`.
- Activation envelopes do not include `as_of`, so safe-mode evaluation can downgrade modes that map to `backtest/dryrun` (`validate|compute-only|paper`) to `execution_domain=backtest` (`compute_context.downgraded=true`, `downgrade_reason=missing_as_of`). This metadata is not limited to `paper`. `shadow` is not downgraded by the missing-`as_of` guard.
- If the activation payload lacks `effective_mode`, Gateway fail-closes to `execution_domain=backtest` and sets `compute_context.safe_mode=true`, `compute_context.downgraded=true`, `compute_context.downgrade_reason=decision_unavailable`.
- On ControlBus relays, Gateway augments outbound payloads before WebSocket fan-out using the same mapping/safe-mode rules as activation HTTP/bootstrap paths.
- ControlBus fan-out injects `phase` (`freeze|unfreeze`), `requires_ack`, and `sequence` via [`ActivationEventPublisher.update_activation_state`]({{ code_url('qmtl/services/worldservice/activation.py#L58') }}). `sequence` is produced per run by [`ApplyRunState.next_sequence()`]({{ code_url('qmtl/services/worldservice/run_state.py#L47') }}).
- `requires_ack=true` currently means Gateway MUST apply the event in-order and publish `ActivationAck` on `control.activation.ack` for that `sequence` (SHALL). This is transport/apply acknowledgement at Gateway, not an end-to-end confirmation from every downstream SDK/WebSocket client.
- Gateway MUST NOT apply later events (especially Unfreeze) or reopen order gates before prior required sequences converge (SHALL). Gap timeout/auto-recovery policy is tracked in [ACK/Gap Resync RFC (Draft)](ack_resync_rfc.md).

Idempotency: consumers must treat older etag/run_id as no-ops. Unknown or expired decisions/activations should default to "inactive/safe".

TTL & Staleness
- DecisionEnvelope includes a TTL (default 300s if unspecified). After TTL, Gateway must treat the decision as stale and enforce a safe default: compute-only (orders gated OFF) until a fresh decision is obtained.
- Activation has no TTL but carries `etag`. Unknown/expired activation -> orders gated OFF.
- `state_hash` is exposed via `GET /worlds/{world_id}/activation/state_hash` and ActivationUpdated events for divergence checks.

---

### 4. Execution Domains & Apply (normative)

- Domains: `backtest | dryrun | live | shadow`.
- Isolation invariants:
  - Cross-domain edges MUST be disabled by default via `EdgeOverride` until a policy explicitly enables them post-promotion.
  - Orders are always gated OFF while `freeze=true` during 2-Phase apply.
  - Domain switch is atomic from the perspective of order gating: `Freeze/Drain -> Switch(domain) -> Unfreeze`.
  - ActivationUpdated acknowledgement flow:
    - Freeze/Drain and Unfreeze phases are emitted with `requires_ack=true`, `phase`, and `sequence` metadata on ControlBus events.
    - Gateway MUST enforce linear replay by `sequence` and MUST NOT relay later events (especially Unfreeze) or reopen gates until prior required sequences are acknowledged (SHALL).
    - Acknowledgements are reported via ControlBus response channels and include `world_id`, `run_id`, `sequence`, and `phase`. They SHOULD advance monotonically per run; out-of-order acknowledgements should be discarded or flagged. Current WorldService apply completion is not hard-blocked on observing the ACK stream.
- 2-Phase Apply protocol (SHALL):
  1. **Freeze/Drain** - Activation entries set `active=false, freeze=true`; Gateway/SDK gate all order publications; EdgeOverride keeps live queues disconnected.
  2. **Switch** - ExecutionDomain updated (e.g., `backtest -> live`), queue/topic bindings refreshed, Feature Artifact snapshot pinned via `dataset_fingerprint`.
  3. **Unfreeze** - WorldService publishes `freeze=false` after Switch. Gateway/SDK keep order gates closed until they apply and acknowledge that unfreeze sequence (SHALL).
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

!!! note "Relationship between the internal canonical schema and presets"
    The `gating_policy` structure in this section defines the **internal canonical schema (SSOT)** of the WorldService policy engine. Core Loop simplification and policy presets aim to reduce the world/policy configuration surface that users must write directly; they are **not intended to reduce the expressiveness** of the gating/risk/observability policies representable by this schema. Presets/overrides and external policy tools should be treated as higher-level interfaces that compile into this canonical schema, and we should be able to re-expose it via separate entry points for advanced/operational flows when needed.

---

## 5. Allocation & Rebalancing APIs (normative)

WorldService exposes two surfaces for coordinated world allocation changes. All flows operate in `mode='scaling'` by default; `overlay` is supported with overlay config and `hybrid` remains unimplemented (HTTP 501).

### 5-A. `POST /allocations` — world allocation upsert

- **Input schema:** [`AllocationUpsertRequest`]({{ code_url('qmtl/services/worldservice/schemas.py#L278') }}). Required fields: `run_id`, `total_equity`, `world_allocations{world_id→ratio}`, and current `positions[]`. Optional knobs include per-world strategy totals (`strategy_alloc_*`), `min_trade_notional`, and symbol lot sizes (`lot_size_by_symbol`).【F:qmtl/services/worldservice/schemas.py†L248-L314】
- **Validation:** `world_allocations` must be non-empty and ratios must remain within [0,1]. Values outside the band raise 422; unsupported modes raise 501.【F:qmtl/services/worldservice/services.py†L184-L207】
- **Core Loop surface:** Runner.submit/CLI query `GET /allocations?world_id=...` for the submitted world to display the **applied world/strategy totals**. Failures are ignored; this is a discovery surface, not an execution trigger.
- **run_id idempotency:** The request body (excluding `run_id`/`execute`/`etag`) is hashed to derive a deterministic `etag`. Reusing a `run_id` with a different payload triggers HTTP 409; matching payloads reuse the stored plan and execution state.【F:qmtl/services/worldservice/services.py†L129-L166】【F:qmtl/services/worldservice/services.py†L207-L236】
- **Plan computation:** `MultiWorldProportionalRebalancer` applies world- and strategy-level scaling to produce `per_world` and `global_deltas`. When strategy totals are omitted, it infers weights from current exposure to operate in “scale-only” mode.【F:qmtl/services/worldservice/rebalancing/multi.py†L1-L111】【F:qmtl/services/worldservice/rebalancing/rule_based.py†L1-L74】
- **Persistence & events:** Successful upserts persist the request/plan snapshot and update stored world/strategy allocations. WorldService then emits `rebalancing_planned` ControlBus events (per world) containing `scale_world`, `scale_by_strategy`, and `deltas`, allowing Gateway to broadcast and measure the rebalance.【F:qmtl/services/worldservice/services.py†L237-L311】【F:qmtl/services/worldservice/controlbus_producer.py†L96-L109】
- **External execution:** When `execute=true` and a rebalance executor is configured, WorldService forwards a normalized `MultiWorldRebalanceRequest` to the executor and stores the response in `execution_response`. Missing executors yield 503; execution failures surface as 502. A successful run marks `executed=true`.【F:qmtl/services/worldservice/services.py†L167-L318】
- **Response:** [`AllocationUpsertResponse`]({{ code_url('qmtl/services/worldservice/schemas.py#L295') }}) returns the computed plan together with `run_id`, `etag`, `executed`, and the optional executor payload.【F:qmtl/services/worldservice/services.py†L212-L235】【F:qmtl/services/worldservice/services.py†L312-L318】

### 5-B. `POST /rebalancing/plan`

- Accepts the same [`MultiWorldRebalanceRequest`]({{ code_url('qmtl/services/worldservice/schemas.py#L236') }}) and runs `MultiWorldProportionalRebalancer`. Requests using `hybrid` return 501. Overlay requests emit `overlay_deltas` alongside the per-world scaling/deltas plus aggregated `global_deltas` for analysis.【F:qmtl/services/worldservice/routers/rebalancing.py†L21-L82】
- The endpoint is stateless—no persistence or audit logging—so operators can preview or simulate plans safely.

### 5-C. `POST /rebalancing/apply`

- Mirrors `/rebalancing/plan` for computation, then serializes the per-world plan and global deltas into the audit store (best effort). When a ControlBus is configured, it publishes `rebalancing_planned` events per world.【F:qmtl/services/worldservice/routers/rebalancing.py†L84-L154】【F:qmtl/services/worldservice/storage/persistent.py†L850-L864】
- `/rebalancing/apply` does not mutate stored allocations. `/allocations` or an external executor perform the actual account changes; this endpoint marks the “approved plan” for observability and audit.

### 5-D. Schema version & alpha metrics handshake

- `/rebalancing/plan` and `/rebalancing/apply` now negotiate a `schema_version` and, when enabled, surface an `alpha_metrics` envelope alongside the per-world plan/global deltas. WorldService exposes the `compat_rebalance_v2` and `alpha_metrics_required` switches through `create_app()` and `WorldServiceServerConfig`, letting operators opt into schema v2 or enforce it per deployment (`compat_rebalance_v2`/`alpha_metrics_required` defaults, toggles, and request gating live in `api.py` and `config.py`). When v2 is disabled the endpoints reply with `schema_version=1` and no metrics; when v2 runs they emit `schema_version=2` plus an `AlphaMetricsEnvelope` even if it is empty so downstream consumers always have a stable dictionary to parse (`AlphaMetricsEnvelope` includes `per_world` and `per_strategy` maps of `alpha_performance` stats). Requests are blocked up front if `alpha_metrics_required` is true and `schema_version<2`, ensuring clients that depend on the richer envelope can fail fast before planning begins.【F:qmtl/services/worldservice/api.py#L119-L210】【F:qmtl/services/worldservice/config.py#L25-L108】【F:qmtl/services/worldservice/routers/rebalancing.py#L54-L187】【F:qmtl/services/worldservice/schemas.py#L245-L308】
- Each `alpha_metrics` map uses `alpha_performance.<metric>` keys (e.g., `alpha_performance.sharpe`, `alpha_performance.max_drawdown`) and defaults to `0.0` when actual data is unavailable, so Gateway/SDK parsers can consume it without extra guards.【F:qmtl/services/worldservice/alpha_metrics.py#L1-L52】
- ControlBus `rebalancing_planned` events carry the negotiated `schema_version` plus the same `alpha_metrics` envelope, giving the Gateway's ControlBus consumer a stable signal to relay the `alpha_performance` metrics (`docs/operations/rebalancing_schema_coordination.md` tracks the coordination steps for Gateway (#1512) and SDK (#1511) before enabling v2).【F:qmtl/services/worldservice/controlbus_producer.py#L27-L52】【docs/operations/rebalancing_schema_coordination.md】

### 5-E. ControlBus integration & metrics

- Gateway’s ControlBus consumer relays `rebalancing_planned` events over the WebSocket `rebalancing` topic and updates Prometheus counters/gauges: `rebalance_plans_observed_total`, `rebalance_plan_last_delta_count`, `rebalance_plan_execution_attempts_total`, `rebalance_plan_execution_failures_total`. These metrics expose plan frequency and execution health.【F:qmtl/services/gateway/controlbus_consumer.py†L223-L276】【F:qmtl/services/gateway/metrics.py†L216-L592】

---

## 6. Security & RBAC

- Auth: service-to-service tokens (mTLS/JWT); user tokens at Gateway -> propagated to WS
- World-scope RBAC enforced at WS; Gateway only proxies
- Audit: all write ops and evaluations are logged with correlation_id

Clock Discipline
- Decisions depend on time. WS uses a monotonic server clock and enforces NTP health. Maximum tolerated client skew should be documented (e.g., <= 2s).

---

## 7. Observability & SLOs

Metrics (current implementation)
- Apply: `world_apply_run_total`, `world_apply_failure_total`
- Allocation snapshots: `world_allocation_snapshot_total`, `world_allocation_snapshot_stale_total`, `world_allocation_snapshot_stale_ratio`
- Risk Hub processing: `risk_hub_snapshot_processed_total`, `risk_hub_snapshot_failed_total`, `risk_hub_snapshot_processing_latency_seconds`
- Validation event processing: `validation_event_processed_total`, `validation_event_failed_total`, `validation_event_processing_latency_seconds`
- Workers: `extended_validation_run_total`, `extended_validation_run_latency_seconds`, `live_monitoring_run_total`
- Domain isolation: `cross_context_cache_hit_total` (target=0; violation blocks promotions)

Alerts
- Decision failures, explicit status polling failures, stale activation cache at Gateway
- cross_context_cache_hit_total > 0 (CRIT): investigate domain mixing before re-enabling apply

---

## 8. Failure Modes & Recovery

- WS down: Gateway returns cached DecisionEnvelope if fresh; else safe default (compute-only/inactive). Activation defaults to inactive.
- Redis loss: reconstruct activation by replaying activation/apply `WorldAuditLog` entries; orders remain gated until consistency is restored.
- Policy parse errors: reject version; keep prior default.

---

## 9. Integration & Events

- Gateway: proxy `/worlds/*`, cache decisions with TTL, enforce `--allow-live` guard
- DAG Manager: no dependency for decisions; only for queue/graph metadata
- ControlBus: WS publishes ActivationUpdated/PolicyUpdated; Gateway subscribes and relays via WS to SDK. Activation relays are augmented (`execution_domain`/`compute_context`) before fan-out; `/events/subscribe` bootstrap activation frames also use the augmentation path.

Runner & SDK Integration (clarification)
- SDK/Runner do not expose execution modes. Callers provide only `world_id` when starting a strategy; Runner adheres to WorldService decisions and activation events.
- `effective_mode` in DecisionEnvelope is computed by WS and treated as input by SDK. Unknown or stale decisions default to compute-only with order gates OFF.
- On submission the Gateway guarantees a **WSB upsert** for each `world_id`, creating or updating a `WorldNodeRef(root)` entry in the WVG.

---

## 10. Testing & Validation

- Contract tests for envelopes (Decision/Activation) using the JSON Schemas (reference/schemas.md).
- Idempotency tests: duplicate/out-of-order event handling based on `etag`/`run_id`.
- WS reconcile tests: initial snapshot vs. `state_hash` divergence handling and HTTP fallback.

{{ nav_links() }}
