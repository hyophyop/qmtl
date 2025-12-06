---
title: "Core Loop-Centric Architecture Roadmap"
tags: [architecture, roadmap, core-loop]
author: "QMTL Team"
last_modified: 2025-12-06
---

# Core Loop-Centric Architecture Roadmap

## 0. Purpose and Scope

This document aggregates the **Core Loop** definition and the As‑Is/To‑Be states described in `architecture.md`, `gateway.md`, `worldservice.md`, `seamless_data_provider_v2.md`, and related specs to define a **project-wide roadmap** for how QMTL should evolve.

- Core Loop (strategy lifecycle)  
  `Author strategy → Submit → (automatic backtest/evaluate/deploy inside a world) → Observe world performance → Refine strategy`
- Goal: Turn the Core Loop **target experience** into reality across code, services, and docs so that users genuinely experience that **“if you focus only on strategy logic, the system optimises and produces returns.”**
- Scope: Provide mid/long-term **architectural direction** and **concrete improvement bundles** across SDK/Runner, WorldService, Gateway/DAG Manager, the data plane (Seamless), operations/observability, and quality/testing/docs.

This is not a Gantt chart with fixed dates but a set of **tracks, priorities, and milestone bundles**. Individual issues/PRs should reference the relevant track/milestone from this roadmap.

## 1. North Star: Core Loop Experience

### 1.1 User Experience Goals

- Strategy authors define only “signal logic + required data + target world”.
- A single `Runner.submit(..., world=..., mode=...)` call:
  - Warms up history and runs replay-style backtests,
  - Computes performance metrics and evaluates policies (WorldService),
  - Produces activation decisions and world-level allocation plans as a **connected pipeline**.
- Users stay in the **“submit → observe → improve” loop** with a unified view over world/strategy contribution and risk.

### 1.2 Hard Constraints for the Roadmap

- **Simplicity > Backward Compatibility**  
  Prefer explicit migration guides over long-lived compatibility flags or dual flows; keep a single “current” path.
- **WorldService/Graph as SSOT**  
  Keep WS/DM as the single sources of truth for policies, decisions, activations, and graph/queue state. SDK/Runner and Gateway remain consumers/boundary layers.
- **Default-Safe**  
  When configuration/decisions are missing or ambiguous, always fall back to compute‑only (backtest, orders gated OFF).

Changes that violate these constraints are not acceptable. When exceptions are unavoidable, record an explicit waiver and follow-up plan in the architecture docs.

## 2. Roadmap Overview: Tracks and Milestones

The roadmap is organised into six tracks. Each track is positioned along the Core Loop and broken down into **P0–P2 priority milestones**.

- T1. Strategy Experience / SDK
- T2. Worlds & Policy (WorldService)
- T3. Data Plane / Seamless
- T4. Gateway / DAG Manager
- T5. Operations, Observability, Safety
- T6. Quality, Testing, Documentation

Each track is structured as “Direction (Design North Star) → Key Milestones (P0–P2) → Concrete Work Examples”.

## 3. T1 — Strategy Experience / SDK Track

### 3.1 Direction

- Make **“knowing Runner.submit is enough”** true for most users by aligning all SDK/Runner flows with the Core Loop.
- Keep strategy code **far away from data/world/domain/queue management**; runtime and services should own environment selection, execution domains, and queue mapping.
- Align `SubmitResult`/CLI output/docs with **world evaluation, decisions, and activations**.

### 3.2 Key Milestones

- **P0‑T1‑M1 — SubmitResult normalisation and Core Loop alignment**
  - Align the Runner.submit/CLI return type with the `DecisionEnvelope`/`ActivationEnvelope` structures so that “submit → inspect evaluation results” is a single object/view.
  - Standardise failures/warnings (e.g., insufficient data, hysteresis not met) into a consistent error/field surface.
- **P0‑T1‑M2 — Execution mode/domain hints removal/normalisation**
  - Remove SDK paths that choose or force `execution_domain` on their own; only domains derived from WorldService decisions are allowed.
  - Explicitly normalise ambiguous modes such as `offline`/`sandbox` to `backtest` and deprecate them in docs.
- **P1‑T1‑M3 — Core Loop-centric templates and guides**
  - Rewrite `guides/strategy_workflow.md`, `guides/sdk_tutorial.md`, and related content so they assume Core Loop as the primary flow.
  - Demote “world-less, standalone backtest” flows to secondary/archived guides if still needed.
- **P2‑T1‑M4 — Advanced patterns (multi-world, shadow execution)**
  - Reframe shadow execution, multi-world strategies, and TagQuery-based multi-asset templates in terms of the Core Loop.

### 3.3 Concrete Work Examples

- `qmtl/runtime/sdk/submit.py`  
  - Refine `SubmitResult` so it is structurally aligned with WorldService `DecisionEnvelope`/`ActivationEnvelope`.
  - Hide purely internal debug fields behind SDK internals; expose only fields meaningful to users.
- `docs/en/guides/strategy_workflow.md` / `docs/ko/guides/strategy_workflow.md`  
  - Rebuild the flow around “Strategy code → Runner.submit → WorldService evaluation → activation reflected in execution”.

## 4. T2 — Worlds & Policy (WorldService) Track

### 4.1 Direction

- Turn WorldService into the **single source of truth for strategy evaluation, activation, and capital allocation policy**.
- Make SDK/Runner and Gateway **thin consumers** that surface WS results verbatim; keep `ValidationPipeline` as a local pre-check/hint layer only.
- Express ExecutionDomain, two-phase apply, and hysteresis semantics identically across docs, code, and runbooks.

### 4.2 Key Milestones

- **P0‑T2‑M1 — Unified evaluation/activation flow**
  - Separate the responsibilities of `ValidationPipeline` vs the WS policy engine and define that “final active/weight/contribution” is solely WS output.
  - Runner.submit/CLI surface WS results as-is and expose ValidationPipeline outputs in a dedicated “local pre-check/extra metrics” section.
- **P0‑T2‑M2 — ExecutionDomain/effective_mode semantics enforced**
  - Fully align code with the ExecutionDomain/effective_mode rules described in `worldservice.md` and `architecture.md`.
  - Enforce default-safe behaviour in WS APIs when `execution_domain` is omitted or ambiguous.
- **P1‑T2‑M3 — Two-phase apply tooling and runbooks**
  - Provide consistent support for two-phase apply (Freeze/Drain → Switch → Unfreeze) across WS, CLI tools, and ops docs.
  - Ensure apply/rollback/audit timelines are visible in WorldAuditLog and dashboards.
- **P2‑T2‑M4 — World-level rebalancing / allocation flow**
  - Connect `/allocations` and the rebalancing engine to the Core Loop “deploy/allocate capital” step, with an operational approval/execute/rollback flow.
  - Surface `/allocations` snapshots (world/strategy totals) from Runner.submit/CLI for the submitted world to make the proposal (evaluation/activation) vs applied (allocation) boundary clear while keeping apply/execute as an auditable ops step (#1817).

### 4.3 Concrete Work Examples

- `qmtl/services/worldservice/*`  
  - Lift `EvaluateRequest`/`DecisionEnvelope`/`ActivationEnvelope` into shared schema modules used by SDK/Runner; remove duplicate type definitions.
  - Add unit tests enforcing default-safe ExecutionDomain/effective_mode behaviour.
- `docs/en/architecture/worldservice.md` / `docs/ko/architecture/worldservice.md`  
  - Keep As‑Is/To‑Be sections synced with the T2 milestones and enrich examples showing how Runner.submit/CLI consume WS results.
- Core Loop contract tests  
  - Extend `tests/e2e/core_loop/test_core_loop_stack.py` with a “submit → allocation summary available” path to lock in the `/allocations` snapshot surface (#1817).

### 4.4 Submit → snapshot → apply operational flow

- `Runner.submit ... --world <id>` surfaces the submitted world’s `/allocations` snapshot (with etag/updated_at) as **read-only context**. When the snapshot is missing or stale, the CLI should hint at `qmtl world allocations -w <id>` for a refresh.
- Operators apply capital changes explicitly via `qmtl world apply <id> --run-id <id> [--plan-file plan.json | --plan '{"activate":[...]}']`. The default is safe/read-only; `run_id` is always required for audit/rollback.
- Apply/rollback approvals stay in the ops lane, and every allocation change should be auditable via etag/run_id. Guidance in the snapshot section must point users through submit → allocations refresh → apply in that order.

<a id="t3-seamless-track"></a>
## 5. T3 — Data Plane / Seamless Track

### 5.1 Direction

- Make the **“data supply automation + market replay backtest”** phases of the Core Loop the responsibility of the Seamless/DataPlane.
- Allow world + preset + a simple data spec to be enough for Runner/CLI to configure appropriate Seamless providers and inject them into StreamInputs.
- Enforce data quality/backfill/SLA/schema guarantees via **Seamless internal pipelines and observability**.

### 5.2 Key Milestones

- **P0‑T3‑M1 — World-based data preset on-ramp**
  - Define world/preset → data preset mapping rules in `world/world.md` and use them in Runner/CLI to auto-configure Seamless instances.
  - Deprecate direct `history_provider` configuration in strategy code where feasible.
- **P1‑T3‑M2 — Schema registry governance**
  - Implement the “canary/strict validation” modes outlined in the Seamless v2 docs and define the rollout flow for schema changes.
  - P‑C / T3 P1‑M2 maps to the following issues:
    - #1150 — registry contracts/validation modes/audit: `SchemaRegistryClient` / `RemoteSchemaRegistryClient`, `validation_mode` / `QMTL_SCHEMA_VALIDATION_MODE`, `QMTL_SCHEMA_REGISTRY_URL`, `seamless_schema_validation_failures_total`, `scripts/schema/audit_log.py`.
    - #1151 — observability/runbook assets: `operations/monitoring/seamless_v2.jsonnet`, `alert_rules.yml` (`SeamlessSla99thDegraded`, `SeamlessBackfillStuckLease`, `SeamlessConformanceFlagSpike`), `scripts/seamless_health_check.py` so dashboards/alerts/health checks are ready to use.
    - #1152 — validation/failure-injection regressions: Hypothesis coverage, failure-injection, and observability snapshot tests (`tests/qmtl/runtime/sdk/test_history_coverage_property.py`, `tests/qmtl/runtime/sdk/test_seamless_provider.py`, `tests/qmtl/foundation/schema/test_registry.py`) run via the command below and are executed in the CI `test` job.

      ```
      uv run -m pytest -W error -n auto \
        tests/qmtl/runtime/sdk/test_history_coverage_property.py \
        tests/qmtl/runtime/sdk/test_seamless_provider.py \
        tests/qmtl/foundation/schema/test_registry.py
      ```
- **P2‑T3‑M3 — Multi-upstream / tag-based queue mapping**
  - Strengthen tag/interval conventions between Gateway/DAG Manager and Seamless to support multi-queue/multi-asset strategies without manual wiring.

### 5.3 Concrete Work Examples

- `docs/en/architecture/seamless_data_provider_v2.md` / `docs/ko/architecture/seamless_data_provider_v2.md`  
  - Add world preset on-ramp rules from the data-plane viewpoint and integrate the archived `rewrite_architecture_docs.md` prescriptions.
- `docs/en/world/world.md` / `docs/ko/world/world.md`  
  - Extend world examples with data preset sections and show how Runner/CLI derive Seamless configurations.

## 6. T4 — Gateway / DAG Manager Track

### 6.1 Direction

- Keep Gateway’s role in the Core Loop as **“single entrypoint for strategy submission + bridge for WS/DM decisions/queue events.”**
- Keep DAG Manager as the SSOT for graphs/nodes/queues, using NodeID/ComputeKey/queue namespaces to guarantee determinism and reuse.
- Implement the ExecutionDomain/ComputeContext semantics from `architecture.md` uniformly across Gateway, DAG Manager, and SDK.

### 6.2 Key Milestones

- **P0‑T4‑M1 — ComputeContext/ExecutionDomain alignment**
  - Fully propagate the canonical rules from `qmtl/foundation/common/compute_context.py` into Gateway `StrategyComputeContext` and DAG Manager consumers.
  - Remove As‑Is code paths where submission `execution_domain` hints override or mix with WS decisions.
- **P0‑T4‑M2 — NodeID / TagQuery determinism**
  - Implement TagQueryNode expansion rules consistently across DM/SDK/Gateway so NodeIDs remain stable as queues are discovered.
- **P1‑T4‑M3 — Queue namespaces and ACLs**
  - Enforce `{world_id}.{execution_domain}.<topic>` naming in production and manage cross-domain access via ACLs.
- **P2‑T4‑M4 — Diff and queue orchestration efficiency**
  - Optimise Diff/queue creation policies to reduce p95 latency under high submission rates.

### 6.3 Concrete Work Examples

- `docs/en/architecture/gateway.md`, `docs/en/architecture/dag-manager.md` (and ko counterparts)  
  - Keep S0‑A As‑Is/To‑Be sections aligned with T4 milestones and update as implementations land.
- `qmtl/services/gateway/submission/context_service.py`  
  - Enforce WS-first ExecutionDomain rules and emit explicit errors/metrics when they are violated.

## 7. T5 — Operations, Observability, Safety Track

### 7.1 Direction

- Provide **observability and determinism** for every Core Loop stage (submission, backtest, evaluation, activation/deploy, allocation).
- Use commit-log/ControlBus/Prometheus/dashboards to make failures and regressions easy to diagnose.
- Apply the default-safe principle consistently: when in doubt, fail or downgrade to compute‑only with orders gated OFF.

### 7.2 Key Milestones

- **P0‑T5‑M1 — Determinism checklist completion**
  - Implement and verify the Determinism checklist items from `architecture.md` (NodeID CRC, NodeCache GC, TagQuery stability, etc.).
- **P1‑T5‑M2 — Core Loop golden-signal dashboards (complete)**
  - Build dashboards that expose key metrics for each Core Loop step (submission latency, backtest coverage, WS evaluation latency, activation propagation, allocation execution) and pin the SLOs/dashboards in `operations/core_loop_golden_signals.md`.
- **P2‑T5‑M3 — Failure playbooks and runbooks**
  - Rework Neo4j/Kafka/Redis/WS failure playbooks in terms of their impact on the Core Loop.

### 7.3 Concrete Work Examples

- `docs/en/operations/monitoring.md`, `docs/en/operations/seamless_sla_dashboards.md`, `docs/en/operations/ws_load_testing.md` (and ko counterparts)  
  - Reorganise metrics/dashboards by Core Loop stage.
- `docs/en/operations/activation.md`, `docs/en/operations/rebalancing_execution.md` (and ko counterparts)  
  - Document rollback/retry strategies from the commit-log viewpoint when activation/allocation fails.

## 8. T6 — Quality, Testing, Documentation Track

### 8.1 Direction

- Prioritise **contract tests** that protect the Core Loop over tests that depend on internal implementation details.
- Use radon, mypy, import-cycle checks, and docs link checks to keep the implementation aligned with architectural commitments.
- Keep i18n docs aligned with `docs/ko` as the canonical source and maintain English (`docs/en`) as accurate translations.

### 8.2 Key Milestones

- **P0‑T6‑M1 — Core Loop contract test suite**
  - Introduce a fast E2E test suite that verifies “strategy submission → WS evaluation/activation → safe execution/gating → results surfaced”.
  - Cover ExecutionDomain default-safe behaviour, WS/Runner SubmitResult alignment, and TagQuery stability.
- **P1‑T6‑M2 — Ongoing radon/complexity management**
  - Apply the `docs/ko/maintenance/radon_c_remediation_plan.md` to Core Loop-sensitive code first.
- **P2‑T6‑M3 — Architecture docs consistency**
  - Consolidate As‑Is/To‑Be content across architecture docs and keep this roadmap cross-linked and up to date.

### 8.3 Concrete Work Examples

- `tests/`  
  - Group Core Loop contract tests under a dedicated module (e.g., `tests/e2e/core_loop`) and ensure CI runs them quickly.
- `docs/en/architecture/architecture.md` / `docs/ko/architecture/architecture.md`  
  - Periodically reconcile As‑Is/To‑Be sections with the actual implementation and update this roadmap alongside.

## 9. Implementation Status (Dec 2025)

- Phases 0–5 in `core_loop_roadmap_tasks.md` / `core_loop_roadmap_tasks2.md` are complete (issues #1755–#1790 closed as of 2025-12-06).
- ExecutionDomain/default-safe vertical is shipped end-to-end (WS validation/downgrade, Runner/CLI hint removal, ComputeContext validators) and locked by contract cases in `tests/e2e/core_loop`.
- SubmitResult now uses shared WS `DecisionEnvelope`/`ActivationEnvelope` schemas as the SSOT with `precheck` separated; CLI/SDK JSON snapshots align with WS and are exercised in the contract suite.
- World-based data preset on-ramp is live (`world.data.presets[]` → Seamless auto-wiring, `--data-preset` option) and covered by the core-loop demo world contract test.
- NodeID/TagQuery determinism and the determinism checklist/metrics/runbook are in place; see `../operations/determinism.md` for response guidance.
- Core Loop golden-signal SLOs/dashboards are anchored in `../operations/core_loop_golden_signals.md`, with architecture/Seamless docs updated to reflect the realised To-Be (T5 P1‑M2 delivered).
- The Core Loop contract suite runs as a CI gate in `.github/workflows/ci.yml` (`CORE_LOOP_STACK_MODE=inproc`), mapping failures back to this roadmap and `../architecture/architecture.md`.

## 10. Operating This Roadmap

- **Issue mapping to tracks/milestones**  
  - Tag new features/refactors/bugfixes with at least one of T1–T6 and a P0–P2 milestone.
- **Keeping As‑Is/To‑Be in sync**  
  - As implementations progress toward To‑Be, update or retire As‑Is sections and adjust the status of related milestones in this roadmap.
- **Visibility for complexity/technical debt**  
  - When exceptions/waivers are required, explain why they diverge from the Core Loop direction in code comments and PR descriptions, and reference follow-up items in this roadmap.

This roadmap serves as the Core Loop-centric reference for QMTL’s mid- to long-term direction. When proposing new work, first decide which track/milestone it belongs to and design it accordingly.
