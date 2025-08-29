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
- 2‑Phase apply: Freeze/Drain → Switch → Unfreeze, idempotent with run_id
- Audit & RBAC: every policy/update/decision/apply event is logged and authorized
- Events: emits activation/policy updates to the internal EventPool

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

---

## 2. API Surface (summary)

CRUD
- POST /worlds | GET /worlds | GET /worlds/{id} | PUT /worlds/{id} | DELETE /worlds/{id}

Policies
- POST /worlds/{id}/policies  (upload new version)
- GET /worlds/{id}/policies   (list) | GET /worlds/{id}/policies/{v}
- POST /worlds/{id}/set-default?v=V

Decisions & Control
- GET /worlds/{id}/decide?as_of=... → DecisionEnvelope
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
  "effective_mode": "dryrun",  
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
  "etag": "act:crypto_mom_1h:abcd:long:42",
  "run_id": "7a1b4c...",
  "ts": "2025-08-28T09:00:00Z"
}
```

Idempotency: consumers must treat older etag/run_id as no‑ops. Unknown or expired decisions/activations should default to “inactive/safe”.

TTL & Staleness
- DecisionEnvelope includes a TTL (default 300s if unspecified). After TTL, Gateway must treat the decision as stale and fall back to a safe mode (offline/backtest) until refreshed.
- Activation has no TTL but carries `etag` (and optional `state_hash`). Unknown/expired activation → orders gated OFF.

---

## 4. Decision Semantics

- Data Currency: now − data_end ≤ max_lag → near‑real‑time; else backtest until caught up
- Sample Sufficiency: metric‑specific minimums (days, trades, bars) gate before scoring
- Gates: AND/OR of thresholds; Score: weighted function; Constraints: correlation/exposure
- Hysteresis: promote_after, demote_after, min_dwell to avoid flapping

The evaluation returns DecisionEnvelope and an optional plan for apply.

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
- Decision failures, apply timeouts, stale activation cache at Gateway

---

## 8. Failure Modes & Recovery

- WS down: Gateway returns cached DecisionEnvelope if fresh; else safe default (offline/backtest). Activation defaults to inactive.
- Redis loss: reconstruct activation from latest snapshot; orders remain gated until consistency restored.
- Policy parse errors: reject version; keep prior default.

---

## 9. Integration & Events

- Gateway: proxy `/worlds/*`, cache decisions with TTL, enforce `--allow-live` guard
- DAG Manager: no dependency for decisions; only for queue/graph metadata
- EventPool: WS publishes ActivationUpdated/PolicyUpdated; Gateway subscribes and relays via WS to SDK

---

## 10. Testing & Validation

- Contract tests for envelopes (Decision/Activation) using the JSON Schemas (reference/schemas.md).
- Idempotency tests: duplicate/out‑of‑order event handling based on `etag`/`run_id`.
- WS reconcile tests: initial snapshot vs. `state_hash` divergence handling and HTTP fallback.

{{ nav_links() }}
