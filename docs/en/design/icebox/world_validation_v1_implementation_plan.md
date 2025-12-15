---
title: "World Validation v1 Implementation Plan"
tags: [design, world, validation, implementation-plan]
author: "QMTL Team"
last_modified: 2025-12-15
status: archived
---

{{ nav_links() }}

# World Validation v1 Implementation Plan

!!! warning "Icebox (reference only, not SSOT)"
    This page is an archived implementation checklist under `docs/en/design/icebox/`.  
    The SSOT is the code/tests and `docs/*/architecture/`. Use this document only for historical context.

!!! abstract "Purpose"
    This document is an implementation plan derived from `world_validation_architecture.md` and
    `model_risk_management_framework.md`, intended as a TODO/checklist to execute “large changes
    without losing the design”.

Related design documents:

- World validation architecture: [world_validation_architecture.md](world_validation_architecture.md)
- Model risk management framework: [model_risk_management_framework.md](model_risk_management_framework.md)

---

## 1. v1 implementation scope summary

v1 targets a stable baseline for **“single strategy + single world validation”**.
Everything else (cohorts/portfolio/stress/live profiles) is explicitly deferred to v1.5+.

## Progress snapshot (for check-ins)

| Phase | Scope | Status | Code references / tests |
|-------|------|--------|--------------------------|
| P1 | EvaluationRun persistence + v1 core metrics block | Done | `qmtl/services/worldservice/storage/*evaluation*`, `tests/qmtl/services/worldservice/test_worldservice_api.py::test_evaluation_run_creation_and_fetch` |
| P2 | RuleResult schema + rule wrapper | Done | `qmtl/services/worldservice/policy_engine.py`, `tests/qmtl/services/worldservice/test_policy_engine.py` |
| P3 | validation_profiles DSL (v1) | Done (backtest/paper profiles + severity/owner overrides) | `policy_engine._materialize_policy`, `tests/qmtl/services/worldservice/test_policy_engine.py::{test_validation_profiles_switch_by_stage,test_validation_profile_overrides_severity_and_owner}` |
| P4 | Persist policy_version / ruleset_hash / recommended_stage in EvaluationRun | Done | metadata plumbing in `decision.py`/`services.py`, `policy_engine.recommended_stage`, `tests/qmtl/services/worldservice/test_worldservice_api.py::test_evaluation_run_creation_and_fetch` |
| P5 | Cohort/Portfolio/StressRule + live monitoring | Done (extended layers, append-only history, live/stress/portfolio metrics, risk_hub snapshot baseline, ControlBus consumer + monitor/worker scripts) | `policy_engine` P5 evaluators + `evaluate_extended_layers`, `worldservice.services._apply_extended_validation`, `extended_validation_worker.py`, `validation_metrics.py`, `risk_hub.py`/`routers/risk_hub.py`/`controlbus_consumer.py`, report (`scripts/generate_validation_report.py`), monitor/worker (`scripts/risk_hub_monitor.py`,`scripts/risk_hub_worker.py`), tests in `tests/qmtl/services/worldservice/` + `tests/qmtl/services/gateway/` + `tests/scripts/test_generate_validation_report.py` |

Test coverage notes:
- Policy/rule metadata: `uv run -m pytest tests/qmtl/services/worldservice/test_policy_engine.py tests/qmtl/services/worldservice/test_worldservice_api.py::test_evaluation_run_creation_and_fetch`
- Record additional WS/GW smoke/integration commands here when run

## Next-step suggestions (v1.5+ hardening)

- Events/ops: production wiring to trigger WS workers from ControlBus/queue-based risk snapshot events (scripts exist; queue wiring is env-dependent).
- Risk hub ops: full producer transition on Gateway (including fills/position sync), standardize blob-store ref format (S3/Redis), continue improving Alertmanager rules/runbooks.
- Regression/perf: run policy diff simulator against a curated “bad strategies” set in CI or periodic batch; add load/perf tests for extended validation workers.
- SDK/docs: add cohort/portfolio/stress/live result lookup guidance in SDK examples and CLI help; link from operator health-check scripts/runbooks.

### New TODOs (v1.5+)
- Connect risk snapshot events to an operational queue (ControlBus/Celery/Arq, etc.) so `ExtendedValidationWorker` and live/stress workers execute idempotently per environment.
- Document and enforce blob-store ref schemas (s3/redis/file), TTL/hash/ACL rules in docs and CI; ship large covariance/returns upload helpers.
- Expand policy-diff / “bad strategy” regression sets (based on `scripts/policy_diff.py`) to produce policy-change impact reports on a schedule.

### 1.1 EvaluationRun / Metrics

- EvaluationRun (WorldService)
  - Required fields: `run_id`, `world_id`, `strategy_id`, `stage`, `risk_tier`
  - Validation metadata: `validation.policy_version`, `validation.ruleset_hash`, `validation.profile`, `summary.status`, `summary.recommended_stage`
- EvaluationMetrics (v1 core only)
  - returns: `sharpe`, `max_drawdown`, `gain_to_pain_ratio`, `time_under_water_ratio`
  - sample: `effective_history_years`, `n_trades_total`, `n_trades_per_year`
  - risk: `adv_utilization_p95`, `participation_rate_p95` (factor_exposures is v1.5+)
  - robustness: `deflated_sharpe_ratio`, `sharpe_first_half`, `sharpe_second_half`
  - diagnostics: `strategy_complexity`, `search_intensity`, `validation_health.metric_coverage_ratio`, `validation_health.rules_executed_ratio`, `returns_source`

### 1.2 Rules / DSL

- Rule types (v1)
  - DataCurrencyRule, SampleRule, PerformanceRule, RiskConstraintRule
  - Evaluate a single EvaluationRun (single strategy). (Cohort/Portfolio/StressRule are v1.5+)
- RuleResult (required fields)
  - `status`, `severity`, `owner`, `reason_code`, `reason`, `tags`, `details`
- World policy DSL (v1)
  - v1 core fields under `validation_profiles.backtest` / `validation_profiles.paper`
  - `default_profile_by_stage.backtest_only/paper_only`
  - `validation.on_error=fail`, `validation.on_missing_metric=fail`
  - Keep the `live` profile and portfolio section as definitions only; they are not used in v1.

### 1.3 MRM / artifacts

- Model Card
  - Minimal required fields: ID/version, purpose, data overview, key assumptions/limitations
- Validation Report (draft format)
  - Summary, Scope/Objective, model summary, profile/rules/metrics used, results, limitations/recommendations
- Override logging
  - Implement only: `override_status`, `override_reason`, `override_actor`, `override_timestamp`

---

## 2. Design section ↔ code module mapping

To avoid losing the design during implementation, map major doc sections to expected code locations. (Names/paths can change; update this table when they do.)

| Design section | Concept | Example target code path |
|--------------|---------|--------------------------|
| §7.1 EvaluationRun | EvaluationRun model/storage | `qmtl/services/worldservice/models/evaluation_run.py` |
| §7.2 EvaluationMetrics | Metrics schema | `qmtl/services/worldservice/schemas/evaluation_metrics.py` |
| §7.3 RuleResult | Rule evaluation results | new model within `qmtl/services/worldservice/policy_engine.py` |
| §7.4 validation_profiles DSL | World policy validation block | DSL parser in `qmtl/services/worldservice/policy_engine.py` |
| §3 ValidationRule interface | Rule implementations/adapters | `policy_engine.py` or `validation_rules.py` |
| §10 Quality targets/SLO | Monitoring metrics | `docs/en/operations/*` + alert_rules.yml |
| §12 Invariants | CI/E2E guardrails | `tests/e2e/core_loop` + new validation tests |

Freeze this mapping early; keep it updated when actual modules move.

---

## 3. Vertical-slice plan

### 3.1 P1 — EvaluationRun persistence (schema only)

Goal:
- Add EvaluationRun model/storage to WorldService and wire `run_id` creation/fetch in Runner.submit.

Scope:
- Add an `evaluation_runs` table/collection (minimal metadata only).
- Add a WS endpoint to fetch EvaluationRuns (internal use).
- Runner.submit → create/link EvaluationRun in WS (surface `SubmitResult.evaluation_run_id`).

Out of scope:
- Full report generation and cohort/portfolio/stress layers.

---

## 4. Invariants (v1 safety bar)

The v1 design must preserve the following invariants:

1. **WS is the SSOT** for stage/mode decisions; SDK/Runner does not self-promote.
2. **Default-safe**: missing/stale decisions downgrade to compute-only/backtest.
3. **No silent live**: live/paper activation requires explicit policy gates and operator intent.

---

## 5. Checklist (v1 completion bar)

Minimum checklist to claim “v1 validation layer is complete”:

- [x] EvaluationRun model/storage exists in WS and Runner.submit surfaces run_id.
- [x] EvaluationMetrics v1 core fields are populated and queryable in WS.
- [x] DataCurrency/Sample/Performance/RiskConstraint rules return RuleResults and are stored on EvaluationRun validation results.
- [x] World policy has validation_profiles.backtest/paper blocks and can make go/no-go decisions with v1 core fields only.
- [x] A draft Validation Report can be auto-generated for at least one world/strategy.
- [x] Invariants (especially 1/2/3) are enforced via CI or e2e tests.

Once this bar is met, treat v1 as complete and plan v1.5+ separately (cohort/portfolio/stress rules, live profiles, portfolio risk, capacity, advanced robustness metrics, etc.).

---

## 6. Risk Signal Hub (exit engine / risk signal hub) addition

`risk_signal_hub` is an SSOT module that provides **portfolio snapshots, risk metrics, and additional exit signals** between execution/allocation (Gateway) and validation/exit (WorldService and Exit Engine).
The goal is to decouple “execution” from “validation/risk signals” so new consumers (like Exit Engine) can integrate without changing SDK/WS surfaces.

### 6.1 Role / data scope

- Inputs (producers): gateway/allocation (actual weights/positions), risk engines (covariance/correlation, stress results), realized return pipelines.
- Outputs (consumers): WS (Var/ES/Sharpe baselines, live monitoring), exit engine (additional exit signals), monitoring dashboards.
- Stored data (example snapshot schema):

  ```json
  {
    "as_of": "2025-01-15T00:00:00Z",
    "weights": {"strat_a": 0.35, "strat_b": 0.25, "strat_c": 0.40},
    "covariance_ref": "cov/2025-01-15",
    "covariance": {"strat_a,strat_b": 0.12, "strat_b,strat_c": 0.15},
    "realized_returns_ref": "s3://.../realized/2025-01-15.parquet",
    "stress": {"crash": {"dd_max": 0.3, "es_99": 0.25}},
    "constraints": {"max_leverage": 3.0, "adv_util_p95": 0.25},
    "provenance": {"source": "gateway", "cov_version": "v42"}
  }
  ```

### 6.2 Interface / deployment shape

- Events: ControlBus (CloudEvents) examples: `risk_snapshot_updated`, `evaluation_run_created`, `evaluation_run_updated`, `validation_profile_changed`. (Extend later if needed.)
- Read view: read-only `get_snapshot(world_id, as_of/version)` APIs over KV/DB/cache (materialized views). Keep large payloads as refs/ids.
- Access control: limit writes to Gateway/risk engines, reads to WS/exit engine/monitoring. Record version/hash/audit logs on updates.

### 6.3 Consumer integration points

- WS: ExtendedValidationWorker reads snapshots to compute Var/ES/Sharpe baselines and portfolio constraint violations.
- Exit engine: uses the same snapshot + market/risk signals to generate exit signals and emit, e.g., `exit_signal_emitted`.
- SDK: no changes; WS/exit engine only read what they need via the hub.

### 6.4 Ops/quality guards

- SLA: snapshot `as_of` lag limit (e.g., 5m). On violation, fall back (previous version + conservative correlation/σ).
- Data contract: required fields (weights, as_of) and optional fields (covariance, realized_returns_ref, stress). Define policies for missing data (e.g., conservative correlation=0.5).
- Security: risk/position snapshots should be in a separate auth domain; auditing required.

### 6.5 Phased rollout

1. Minimal: Gateway writes snapshots to KV/DB; WS/exit engine only reads.
2. Event-driven: publish events on ControlBus/Kafka; subscribe in workers to update/trigger.
3. Extend: combine covariance/stress results via refs/ids; manage exit-signal emission through the same hub.

### 6.6 Rework hooks (hub integration)

- Portfolio Var/ES: replace direct Gateway dependencies with hub lookups for weights/correlation/covariance.
- Stress/live re-sim workers: schedule via hub events (e.g., `risk_snapshot_updated`) → ControlBus/queue-based background workers.
- Replace fire-and-forget async hooks with an operational queue (Celery/Arq, etc.) or event handlers to achieve hub-event → queue → WS-worker execution.
- Update CI/ops checklists to enforce hub contracts (required fields, as_of/version, TTL) and fail-closed policies for high-risk worlds.
- Exit engine integration: generate exit signals from hub events and publish on ControlBus/Kafka; define apply priority/override policies in ops docs. (See: [exit_engine_overview.md](exit_engine_overview.md).)
- Dev/prod templates: dev uses in-memory/SQLite metadata and fakeredis/in-memory cache only (no file/S3 persistence); prod uses Postgres+Redis cache+object storage+Kafka/ControlBus. WS/exit engine should use the same API/events to abstract env differences.
  - Use a `risk_hub` block in `qmtl.yml` to configure WS router token/inline thresholds/blob-store and Gateway producer clients together to avoid drift. (In dev profiles, do not enable persistent blob stores.)
- Freeze the phased workflow:
  1) **Hub minimal**: snapshot write/read API + `risk_snapshot_updated` event.
  2) **Gateway producer transition**: after rebalance/fill, write weights+covariance ref/matrix+as_of (removes WS direct dependencies).
  3) **WS consumer transition**: ExtendedValidation/live/stress workers compute via hub lookups/subscriptions.
  4) **Exit/monitoring**: exit engines and dashboards subscribe only to hub events, without SDK/WS changes.
  - Current status: WS has `risk_hub` router + ExtendedValidationWorker hub lookups, binding persistence via `risk_snapshots` in dev (in-memory/SQLite) and prod (Postgres/Redis). Event publish/queue wiring and full Gateway producer rollout are tracked as follow-ups.
  - Ops visibility: risk-hub freshness/missing metrics (`risk_hub_snapshot_lag_seconds`, `risk_hub_snapshot_missing_total`), Alertmanager rules, runbooks/health scripts (`risk_signal_hub_runbook.md`, `scripts/risk_hub_monitor.py`), and an example ControlBus worker (`scripts/risk_hub_worker.py`).

{{ nav_links() }}
