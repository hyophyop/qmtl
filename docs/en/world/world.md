# QMTL Worlds — Strategy Lifecycle Specification v1

This document introduces the “World” abstraction to QMTL with minimal
disruption. The aim is to reuse existing components (DAG Manager, Gateway, SDK
Runner, metrics) while enabling policy‑driven automatic evaluation, promotion,
and demotion.

> **Terminology:** "World" is the authoritative term throughout QMTL. The
> previously proposed rename to "Realm" was shelved and is retained only as an
> archived design note for historical context.

- References: `docs/architecture/architecture.md`, `docs/architecture/gateway.md`,
  `docs/architecture/dag-manager.md`
- Repo boundary: only reusable utilities/nodes/gateway extensions live under
  `qmtl/`. Strategy (alpha) implementations belong under repository‑root
  `strategies/`.
- Data handler baseline (#1653): `SeamlessDataProvider` (`qmtl/runtime/sdk/seamless_data_provider.py`) is the default data handler for history/backfill flows. Do not replace the default; extend or wrap it via the seamless presets/plugins described in [Seamless DP v2](../architecture/seamless_data_provider_v2.md) when customization is required.

## 0. Core Loop Summary

This spec positions World as the **strategy lifecycle management unit** and ties
it directly into the Core Loop in four stages:

1. Strategy submission → binding to a World (`Runner.submit(..., world=...)` / `/worlds/{id}/decisions` / WSB)
2. World evaluation (`/worlds/{id}/evaluate`) → DecisionEnvelope (active/violations)
3. Activation/gating (`/worlds/{id}/activation` + ControlBus) → order‑path control
4. Capital allocation (`/allocations` + `/rebalancing/*`) → world/strategy allocations  

Connection points to Runner.submit / CLI (inputs: returns/metrics; outputs:
status/weight/contribution) are sketched in the sections below so this single
document explains the **world‑first Core Loop** without heavy cross‑navigation.

## 1. Scope and Non‑Goals

Objectives
- Treat World as the top‑level abstraction. Evaluate/select strategies and
  manage execution modes based on a versioned WorldPolicy.
- Combine data currency, sample sufficiency, performance thresholds,
  correlation/risk constraints, and hysteresis to drive promotion/demotion.
- Keep Runner as the single entry for world‑driven execution while using the
  existing Gateway/DAG Manager/metrics surfaces.

Non‑goals (initial)
- No new distributed scheduler, message broker, or graph model.
- Strategy deployment/process management remains outside this spec; the focus is
  “selection/transition plan + activation gate”.

## 2. Concepts and Data

- World: portfolio boundary and execution scope (e.g., `world_id="crypto_mom_1h"`).
- WorldPolicy (vN): versioned YAML snapshot; parsed/validated on load.
- StrategyInstance: per‑(strategy, params, side, world) instance.
- Activation Table: Redis hash `world:<id>:active` storing active strategies and
  weights.
- Audit Log: snapshots of inputs, decisions (Top‑K/promote/demote), and 2‑phase
  apply results in the Gateway DB backend (Postgres/SQLite/memory).

Recommended locations
- Policies: `config/worlds/<world_id>.yml`
- Activation: `world:<world_id>:active` (Redis)
- Audit/versions: tables in the Gateway DB

## 3. States and Transitions (Minimal)

- Execution follows WorldService decisions; Runner does not choose modes.
- Track ops‑level world states: `evaluating` / `applying` / `steady`.
- Two‑phase transitions
  1) Freeze/Drain: enable order gate; optionally flatten or carry positions
  2) Switch: replace activation set (Top‑K) and reflect gate state in Runner
  3) Unfreeze: disable order gate
  All steps are idempotent via `run_id`; failures leave a rollback point.

## 4. Policy DSL (Concise)

Minimal YAML stages: Gates → Score → Constraints → Top‑K → Hysteresis.

```yaml
# config/worlds/crypto_mom_1h.yml
world: crypto_mom_1h
version: 1

data_currency:
  max_lag: 5m        # validate if now - data_end <= 5m; else compute-only until caught up
  min_history: 60d   # metrics remain advisory until met
  bar_alignment: exchange_calendar

selection:
  gates:
    and:
      - sample_days >= 30
      - trades_60d >= 40
      - sharpe_mid >= 0.60
      - max_dd_120d <= 0.25
  score: "sharpe_mid + 0.1*winrate_long - 0.2*ulcer_mid"
  topk:
    total: 8
    by_side: { long: 5, short: 3 }
  constraints:
    correlation:
      max_pairwise: 0.8
    exposure:
      gross_budget: { long: 0.60, short: 0.40 }
      max_leverage: 3.0
      sector_cap: { per_sector: 0.30 }
  hysteresis:
    promote_after: 2
    demote_after: 2
    min_dwell: 3h

position_policy:
  on_promote: flat_then_enable
  on_demote: disable_then_flat
```

## 5. Decision Flow (Summary)

Data currency → Gates → Score → Constraints → Top‑K → Hysteresis

## 6. Order Gate (Lightweight)

- Form: shared SDK `ProcessingNode` (e.g., `OrderGateNode`).
- Behavior: at execution time, query the Gateway activation table (HTTP/WS) and
  drop or zero orders when inactive.
- Benefit: minimal intrusion; supports 2‑phase transitions safely.
- Placement: immediately before brokerage nodes; default is conservative (block
  unless active).

Activation API (minimal)
- GET `/worlds/{world_id}/activation?strategy_id=...&side=...` → `{ active, weight }`
- WS broadcast (optional) on updates

## 7. Operations and Safety (Required)

- Data currency gate: keep compute‑only until `now - data_end <= max_lag`.
- Sample sufficiency: metrics advisory until minimums are met.
- Two‑phase transition: Freeze/Drain → Switch → Unfreeze, idempotent `run_id`.
- Risk circuit: gate ON on world‑level drawdown/VAR/leverage violations.
- Alerts: standardize promotion/demotion/apply failure/latency/circuit events.

Suggested SLOs
- `world_eval_duration_ms_p95`, `world_apply_duration_ms_p95`
- `world_activation_skew_seconds`
- `promotion_fail_total`, `demotion_fail_total`

## 8. Multi‑world and Resources

- Start with World‑SILO isolation; consider shared nodes later to reduce cost.
- When shared nodes are introduced, enforce boundaries with NodeID hashing and
  namespaces; perform Mark‑&‑Sweep with drain.

## 9. Phased Rollout (Work Items)

Phase 0 — docs/metric prep
- Add this spec and sample policies under `config/worlds/*.yml`.
- Ensure performance metric nodes or existing metrics are sufficient.

Phase 1 — read‑only evaluator + activation table
- Gateway: WorldPolicy parser/validator and audit schema.
- Gateway: `GET /worlds/{id}/activation`, `POST /worlds/{id}/evaluate` (dry‑run).
- Scripts: `scripts/world_eval.py` for CLI evaluation.

Phase 2 — 2‑phase applier + safety
- Gateway: `POST /worlds/{id}/apply` implementing Freeze/Drain → Switch → Unfreeze.
- Gateway: risk circuit switch (immediate gate OFF on violations).
- Gateway: metrics/alerts for promotion/demotion/failure/latency.

Phase 3 — SDK order gate (optional)
- SDK: add `OrderGateNode`.
- Examples: update docs with gate insertion.

Phase 4 — multi‑world optimization (optional)
- Gateway: shared node namespaces/partition views; Mark‑&‑Sweep with drain.
