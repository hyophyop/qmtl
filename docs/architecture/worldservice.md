---
title: "WorldService — World Policy, Decisions, and Activation"
tags: [architecture, world, policy]
author: "QMTL Team"
last_modified: 2025-08-29
---

{{ nav_links() }}

# WorldService — World Policy, Decisions, and Activation

## 0. Role & Scope

WorldService is the system of record (SSOT) for Worlds. It owns:
- World/Policy registry: CRUD, versioning, defaults, rollback
- Decision engine: data-currency, sample sufficiency, gates/score/constraints, hysteresis → effective_mode
- Activation control: per-world activation set for strategies/sides with weights
- ExecutionDomain as a first-class concept: `backtest | dryrun | live | shadow` per world
- 2‑Phase apply: Freeze/Drain → Switch → Unfreeze, idempotent with run_id
- Audit & RBAC: every policy/update/decision/apply event is logged and authorized
- Events: emits activation/policy updates to the internal ControlBus

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
- Key: world:<id>:active → { strategy_id|side : { active, weight, etag, run_id, ts } }
- Snapshots periodically persisted to DB for audit

WorldAuditLog (DB)
- id, world_id, actor, event (create/update/apply/evaluate/activate/override)
- request, result, created_at, correlation_id

### 1‑A. WVG Data Model (normative)

WorldService is the SSOT for the World View Graph (WVG), a per‑world overlay referencing global GSG nodes (Global Strategy Graph=GSG):

- WorldNodeRef (DB): `(world_id, node_id, execution_domain)` → `status` (`unknown|validating|valid|invalid|running|paused|stopped|archived`), `last_eval_key`, `annotations{}`
- Validation (DB): `eval_key = blake3:(NodeID||WorldID||ContractID||DatasetFingerprint||CodeVersion||ResourcePolicy)` (**'blake3:' prefix required**), `result`, `metrics{}`, `timestamp`
- DecisionEvent (DB/Event): `event_id`, `world_id`, `node_id`, `decision` (`stop|pause|resume|quarantine`), `reason_code`, `scope` (default `world-local`), `propagation_rule`, `ttl`, `timestamp`
- **WvgEdgeOverride (DB):** 월드-로컬 도달성 제어 레코드. `(world_id, src_node_id, dst_node_id, active=false, reason)` 형태로 특정 월드에서 비활성화할 에지를 명시한다.

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

Decisions & Control
- GET /worlds/{id}/decide?as_of=... → DecisionEnvelope
- POST /worlds/{id}/decisions       (post operational DecisionEvent; default scope=world-local)
- GET /worlds/{id}/activation?strategy_id=...&side=... → ActivationEnvelope
- PUT /worlds/{id}/activation          (manual override; optional TTL)
- POST /worlds/{id}/evaluate           (plan only)
- POST /worlds/{id}/apply              (2‑Phase apply; requires run_id)
- GET /worlds/{id}/audit               (paginated stream)

RBAC: world-scope roles (owner, reader, operator). Sensitive ops (`apply`, `activation PUT`) require operator.

---

## 3. Envelopes (normative)

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
- `weight` soft‑scales sizing in the range [0.0, 1.0]. If absent, default is 1.0 when `active=true`, else 0.0.
- `effective_mode` communicates compute mode to SDK/UI (`compute-only|paper|live`). Gateway/SDK map this to an ExecutionDomain for compute and routing: `compute-only → backtest`, `paper → dryrun`, `live → live`. `shadow` is reserved for parallel validation against live feeds without publishing orders.

Idempotency: consumers must treat older etag/run_id as no‑ops. Unknown or expired decisions/activations should default to “inactive/safe”.

TTL & Staleness
- DecisionEnvelope includes a TTL (default 300s if unspecified). After TTL, Gateway must treat the decision as stale and enforce a safe default: compute‑only (orders gated OFF) until a fresh decision is obtained.
- Activation has no TTL but carries `etag` (and optional `state_hash`). Unknown/expired activation → orders gated OFF.

---

### 4. Execution Domains & Apply (normative)

- Domains: `backtest | dryrun | live | shadow`.
- Isolation invariants:
  - Cross‑domain edges MUST be disabled by default via `WvgEdgeOverride` until a policy explicitly enables them post‑promotion.
  - Orders are always gated OFF while `freeze=true` during 2‑Phase apply.
  - Domain switch is atomic from the perspective of order gating: `Freeze/Drain → Switch(domain) → Unfreeze`.
- Queue namespace guidance: operationally, topics MAY be organized under `{world_id}.{execution_domain}.<topic>` namespaces with ACLs to prevent accidental cross‑domain consumption. This does not change NodeID semantics and remains a deployment choice.

---

## 4. Decision Semantics

- Data Currency: now − data_end ≤ max_lag → near‑real‑time; else compute‑only replay until caught up (orders remain gated OFF)
- Sample Sufficiency: metric‑specific minimums (days, trades, bars) gate before scoring
- Gates: AND/OR of thresholds; Score: weighted function; Constraints: correlation/exposure
- Hysteresis: promote_after, demote_after, min_dwell to avoid flapping

The evaluation returns DecisionEnvelope and an optional plan for apply.

### 4‑A. Operational Decision Events (WVG)

- Default scope is `world-local` (MUST). Non‑local scopes require explicit `scope`, `propagation_rule`, and `ttl`, and follow an approval workflow before consumption.
- DecisionEvent targets a `node_id` (strategy root allowed). Effects are world‑scoped unless propagation explicitly applies.
- Storage: DecisionEvents are recorded in WS (DB) and published on ControlBus with an `etag`.

### 4‑B. EvalKey and Validation Caching

- EvalKey = `blake3(NodeID || WorldID || ExecutionDomain || ContractID || DatasetFingerprint || CodeVersion || ResourcePolicy)`
- Any change in the components invalidates cache and triggers re‑validation.

---

## 5. 2‑Phase Apply

1) Freeze/Drain (orders gated OFF)
2) Switch (activation set swap, weights applied)
3) Unfreeze (orders gated ON)

Each apply carries a run_id and is idempotent. On failure, revert to previous activation snapshot.

Concurrency & Single‑Flight
- At most one apply per `world_id` in flight; subsequent applies return 409 or are queued.
- Updates use optimistic concurrency via `resource_version`/`etag` on activation sets.

---

## 6. Security & RBAC

- Auth: service‑to‑service tokens (mTLS/JWT); user tokens at Gateway → propagated to WS
- World‑scope RBAC enforced at WS; Gateway only proxies
- Audit: all write ops and evaluations are logged with correlation_id

Clock Discipline
- Decisions depend on time. WS uses a monotonic server clock and enforces NTP health. Maximum tolerated client skew should be documented (e.g., ≤ 2s).

---

## 7. Observability & SLOs

Metrics example
- world_decide_latency_ms_p95, world_apply_duration_ms_p95
- activation_skew_seconds, promotion_fail_total, demotion_fail_total
- registry_write_fail_total, audit_backlog_depth

Skew Metrics
- `activation_skew_seconds` is measured as the difference between the event `ts` and the time the SDK processes it, aggregated p95 per world.

Alerts
- Decision failures, explicit status polling failures, stale activation cache at Gateway

---

## 8. Failure Modes & Recovery

- WS down: Gateway returns cached DecisionEnvelope if fresh; else safe default (compute‑only/inactive). Activation defaults to inactive.
- Redis loss: reconstruct activation from latest snapshot; orders remain gated until consistency restored.
- Policy parse errors: reject version; keep prior default.

---

## 9. Integration & Events

- Gateway: proxy `/worlds/*`, cache decisions with TTL, enforce `--allow-live` guard
- DAG Manager: no dependency for decisions; only for queue/graph metadata
- ControlBus: WS publishes ActivationUpdated/PolicyUpdated; Gateway subscribes and relays via WS to SDK

Runner & SDK Integration (clarification)
- SDK/Runner do not expose execution modes. Callers provide only `world_id` when starting a strategy; Runner adheres to WorldService decisions and activation events.
- `effective_mode` in DecisionEnvelope is computed by WS and treated as input by SDK. Unknown or stale decisions default to compute-only with order gates OFF.
- 제출 시 Gateway는 각 `world_id`에 대해 **WSB upsert**를 보장하며, WVG에 `WorldNodeRef(root)`를 생성/갱신한다.

---

## 10. Testing & Validation

- Contract tests for envelopes (Decision/Activation) using the JSON Schemas (reference/schemas.md).
- Idempotency tests: duplicate/out‑of‑order event handling based on `etag`/`run_id`.
- WS reconcile tests: initial snapshot vs. `state_hash` divergence handling and HTTP fallback.

{{ nav_links() }}
