---
title: "Strategy/Node Distillation — Design Sketch"
tags: [design, distillation, world, validation, governance]
author: "QMTL Team"
last_modified: 2025-12-30
status: draft
---

{{ nav_links() }}

# Strategy/Node Distillation — Design Sketch

!!! warning "Icebox (Reference-only)"
    This document lives under `docs/en/design/icebox/` and is **not an active work item/SSOT**. Use it for background/reference only; promote adopted parts into `docs/en/architecture/` or code/tests.

## 0. Goals

Design a path where “as strategies/nodes accumulate in QMTL, patterns and operational rules that humans used to enforce manually are progressively automated (distilled)”.

The core is **WorldService policy/validation/governance**, not the UI:

- The UI is an observation/approval surface (consumer).
- The SSOT for distillation is `EvaluationRun` + `Evaluation Store` + WorldPolicy (DSL).
- Recommendations must never replace decisions; they must remain reviewable/auditable/rollbackable.

Related docs:

- World spec: [world/world.md](../../world/world.md)
- Core Loop × WorldService (promotion governance): [architecture/core_loop_world_automation.md](../../architecture/core_loop_world_automation.md)
- World validation layer (icebox): [world_validation_architecture.md](world_validation_architecture.md)
- MRM framework (icebox): [model_risk_management_framework.md](model_risk_management_framework.md)
- Evaluation Store operations: [operations/evaluation_store.md](../../operations/evaluation_store.md)
- Determinism runbook (run_manifest/NodeID/TagQuery): [operations/determinism.md](../../operations/determinism.md)
- UI (icebox, observation surface): [qmtl_ui.md](qmtl_ui.md)

---

## 1. Scope and non-goals

### 1.1 In scope

- Concept model for distillation (facts/decisions/recommendations)
- How distillation outputs connect to World policy/validation/governance
- A minimal data model/interface sketch that can evolve from v0 → v1

### 1.2 Out of scope

- Arguing alpha validity for a specific strategy idea (strategy repo / KB territory)
- Full implementation details of any specific method (PBO/CSCV/DSR/bootstrap)
- Forcing new large infrastructure components (new broker/DB, etc.)

---

## 2. Core principles (“fixed points” for wall-street-grade upgrades)

Distillation should not be “automation to squeeze more alpha”, but a path that **productizes failure modes and operational rules**.

1. **Integrity first**
   - If accounting/reporting is inconsistent (e.g., daily sums ≠ trades sums), distillation/promotion judgment for that region defaults to “forbidden/deferred”.
2. **Execution realism is locked**
   - Cost/slippage/fill assumptions are sealed per run (run_manifest). Candidates are defined by “survives conservative assumptions”, not by “looks good”.
3. **Overfitting control is measured, not felt**
   - DSR/PSR, (optional) CSCV-based PBO, bootstrap success probabilities are treated as **gates** (pass/fail/warn) before they are ever treated as scores.
4. **Separate alpha, risk, execution**
   - Prefer reuse/standardization at the node/gate/risk-shell level over whole-strategy cloning.
5. **Fail-closed + auditable (append-only)**
   - The system stays conservative even without recommendations; every recommendation/approval/apply/rollback must be traceable via `Evaluation Store` / audit logs.

---

## 3. Concept model: Facts / Decisions / Recommendations

To make distillation accumulate as “stable organizational knowledge”, never mix the three layers below.

### 3.1 Facts (observations; immutable inputs)

- `EvaluationRun` + `EvaluationMetrics` (returns/sample/risk/robustness/diagnostics)
- Run reproducibility inputs (run_manifest):
  - data snapshot/preset, code/node versions, fee/slippage/fill profile, seeds/rounding rules, etc.
- Execution/ops facts:
  - risk_signal_hub snapshots (ref/inline), fill/position events, cost aggregations, override events, ex-post failures

Facts must be reproducible/recomputable, and updates are allowed only as new revisions (append-only).

### 3.2 Decisions (policy/approval/apply results; SSOT)

- WorldPolicy (DSL) and versioning
- activation/allocation apply results (2-phase apply) and failure/rollback logs
- override approvals and re-review outcomes (with due dates and rationale)

### 3.3 Recommendations (distillation outputs; suggestions)

Suggestions emitted by a distiller that are consumable by humans/policy:

- Strategy-level:
  - `promote_candidate`, `demote_candidate`, `needs_review`, `paper_only_recommended`, etc.
- Node/gate-level:
  - `bless_node_template`, `recommend_risk_shell`, `recommend_metric_gate`, `flag_data_leak_risk`, etc.

Recommendations must always:

- include **evidence** (which Facts they are grounded in),
- never auto-apply outside the governance boundary,
- carry a reviewable state machine (approve/reject/defer).

---

## 4. Data model (sketch)

To accumulate distillation outputs as “knowledge”, you want queryable/compareable objects, not just logs.

Recommendation: store them as **append-only revisions**, aligned with the Evaluation Store model.

```text
DistillationRun
  - distillation_run_id
  - world_id
  - as_of (UTC)
  - input_window (start/end)
  - distiller_version
  - inputs_ref (optional, offload)
  - created_at

DistillationRecommendation (append-only, revisioned)
  - world_id
  - subject_type: strategy|node_template|risk_shell|metric_gate
  - subject_id: strategy_id|node_template_id|...
  - action: bless|promote|demote|add_gate|tighten_gate|defer|investigate
  - status: proposed|approved|rejected|applied|superseded
  - score: float (optional)
  - confidence: low|medium|high
  - evidence:
      - evaluation_run_ids[]
      - key_metrics_snapshot
      - invariants_passed: bool
      - overfit_controls: {dsr, pbo, bootstrap_probs, ...}
      - execution_profile: {fee_model, slippage_model, stress_grid, ...}
      - notes
  - governance:
      - actor (on approve/reject)
      - reason
      - timestamp
  - created_at
```

---

## 5. Distillation pipeline (sketch)

For safety, distillation should be decomposed into **gates → ranking → recommendations**, rather than a single “score model”.

### 5.1 Step 0 — define input windows and candidate sets

- Per world:
  - lock observation windows (e.g., last 90d backtest + last 30d paper)
  - group variants into cohort/campaigns to reflect search intensity (same experiment family)

### 5.2 Step 1 — integrity gate (highest priority)

- If an accounting/aggregation invariant is violated:
  - exclude the run from distillation inputs
  - emit `flag_integrity_issue` recommendations to route into triage

### 5.3 Step 2 — execution realism gate (conservative stress)

- With locked fee/slippage/funding profiles:
  - measure sensitivity to stress grids (+bps, spread widening, etc.)
- Patterns like “tiny per-trade edge with too many trades” should be separated into:
  - “paper-forward needed” or “more conservative fill model needed” execution recommendations,
  rather than being mixed into a single score.

### 5.4 Step 3 — overfitting-control gate (required before promotion)

- Using DSR/PSR, (optional) PBO/CSCV, and bootstrap success probabilities:
  - assign `blocking/warn/info` states.
- This must align with WorldPolicy validation gates, and should be persisted as policy/rule outcomes (not buried inside a score).

### 5.5 Step 4 — stability/contribution estimation (node/gate level)

The core of “automatic distillation” is extracting reusable primitives below “entire strategy”.

- **Node/feature contribution (e.g., ablation uplift)**
  - record delta when toggling a specific node/gate on/off within the same strategy
  - aggregate at cohort level to surface “only works in regime X”
- **Risk shell effect**
  - accumulate one-axis experiments that keep alpha fixed and only change risk budgeting/kill-switches,
    then elevate “bankruptcy removed in HV” combinations as templating candidates.

### 5.6 Step 5 — recommendation generation and governance queueing

- Always emit human-readable “why now”:
  - broken invariants, regime collapse signals, slippage sensitivity, overfit signals, etc.
- Merge approve/reject/defer and rationale into MRM/ops workflows.

---

## 6. Integration points (only through SSOT paths)

```mermaid
flowchart TD
  Facts[EvaluationRun & Metrics\n(run_manifest locked)] --> Store[(Evaluation Store)]
  Store --> Distiller[Distiller\n(batch or worker)]
  Distiller --> Reco[Recommendations\n(append-only)]
  Reco --> Gov[Governance\n(approve/reject/override)]
  Gov --> Policy[WorldPolicy changes\n+ Apply plan]
  Policy --> WS[WorldService decision/activation]
  UI[UI/Report] --> Store
  UI --> Reco
```

- The distiller can start as a WS-internal worker or as an offline batch script that writes into the same schema.
- Application must always happen through:
  - (A) WorldPolicy versioned changes, or
  - (B) activation/allocation apply,
  never by “recommendation implies apply”.

---

## 7. Incremental rollout (v0 → v1)

### v0 (quick start)

- A batch script:
  - reads recent EvaluationRuns,
  - produces recommendation reports (Markdown/JSON) as artifacts.
- Humans read and (if needed) change WorldPolicy manually.

### v1 (productize)

- Persist recommendations into Evaluation Store:
  - keep approve/reject/apply states and rationale as append-only revisions.
- CI/ops gates:
  - if integrity invariants break, do not generate promotion candidates
  - for policy changes, follow the existing Independent Validation policy-diff workflow

---

## 8. Strategy-author view: minimal “distillable” contract (draft)

Strategies can be implemented freely as DAGs, but for automatic distillation to work as “cumulative learning”, we need a **minimal shared contract**.
This does not mean “strategy authors must provide raw datasets” — it means **World/Runner lock reproducible inputs and a standard output boundary**.

!!! warning "Upfront review required (concerns)"
    The proposals in §8–§10 are a draft for a “minimal distillable contract”. **Do not promote them into SSOT (architecture/operations/code) or start implementation without careful upfront review.**  
    In particular, (1) asset-class-specific input contracts (data presets/snapshots/calendars/fees/funding, etc.) and (2) ablation rules (DAG rewrite/stubs) have a high risk of conflicting with execution pipelines, determinism (run_manifest), and data-contamination boundaries. Introduce them incrementally after reviewing per asset class and world tier.

### 8.1 The minimum unit of “raw data” is a World preset, not a strategy

From a distillation perspective, the minimal “raw data” requirement is not “a file/table”, but **declaring and using a World preset**:

- Worlds declare the data-plane SSOT via `data.presets[]`. (See [world/world.md](../../world/world.md) §6.2)
- Execution converges on `Runner.submit(..., world=..., data_preset=...)`. (See [guides/strategy_workflow.md](../../guides/strategy_workflow.md))
- `StreamInput` should usually rely on preset-based auto-wired `history_provider`; arbitrary custom providers should remain an “experiment/legacy” path.

In short: to be distillable, a run must seal in its run_manifest **(A) which dataset/preset was used** and **(B) which snapshot/as-of (fingerprint) it refers to**.

### 8.2 Minimal “final trading signal” boundary: prefer intent-first

The internal graph (e.g., z-score calculation) can be anything, but World/validation/distillation need a consistent boundary for “what did the strategy intend to trade”.

Recommended baseline:

- Emit **position targets (Intent)** rather than direct orders.
- Use `PositionTargetNode` and the `make_intent_first_nodeset` recipe as the default path.

See:

- Intent-based target API: [reference/intent.md](../../reference/intent.md)

At minimum, distillation/validation must be able to identify:

- (1) an “alpha/signal” node (e.g., z-score / alpha score)
- (2) an “intent/target” node (position targets; input to the execution pipeline)

NodeID alone may not be enough to infer those boundaries, so §8.4 (semantic metadata) is required.

### 8.3 How to surface hints while authoring (proposal): Distillation Readiness Check

Instead of relying on the UI, it’s more effective to expose “does my DAG meet the distillation contract?” via **CLI/SDK preflight checks**.

Proposed surfaces (examples):

- `qmtl submit --lint distillation` (pre-submit checks)
- `qmtl tools sdk doctor --distillation` (DAG/nodeset diagnostics)
- `Runner.submit(..., strict_distillation=True)` (escalate warnings to failures in dev worlds)

Draft checks:

- World/preset: `world` and `data_preset` are specified and the preset exists in the world
- Input determinism: `dataset_fingerprint`/`as_of`/interval alignment is present (avoids default-safe downgrades)
- Output boundary: intent-first target node exists (or at least an explicit “intent boundary” is declared)
- Execution assumptions: fee/slippage (and funding when applicable) profiles are sealed into the run_manifest
- Banned patterns (examples): multi-upstream / extra-feed contamination is absent (or the run is labeled “non-distillable”)

The output should include “why distillation is blocked” plus “quick-fix” suggestions (wrap `alpha_node` in a `PositionTargetNode`, add a world preset, etc.).

### 8.4 Minimal metadata for node distillation (draft)

Node distillation needs to know “what role does this node play”. Relying on implicit inference from code becomes brittle, so we recommend **lightweight declarative metadata**.

Proposed minimal fields (examples):

- `semantic_role`: `raw_input|feature|signal|intent|risk_shell|execution`
- `family`: conceptual family (e.g., `zscore`, `atr_gate`, `rsi_filter`)
- `ablation_group`: a grouping key that should be ablated together (e.g., `mr_leg`, `risk_shell_v1`)

Start with a tag convention compatible with `StreamInput(tags=[...])` / TagQuery, and promote into a formal node-schema `metadata` field once stable.

---

## 9. Ablation for node impact: how to avoid breaking the DAG (draft)

### 9.1 Problem: “if you remove a node, downstream breaks”

If a strategy author manually removes a node to measure its effect, downstream nodes that consume it will break immediately.
In DAGs where one node output is combined in multiple downstream paths, manual ablation is structurally fragile.

Therefore, ablation should be handled as **system-generated DAG variants**, not as “edit the strategy code”.

### 9.2 Solution: DAG rewrite + schema-preserving stubs

The distillation/validation pipeline should generate separate DAGs for the baseline and the ablation variant.

- Do not delete the node.
- Replace it with a **stub node that preserves the output schema**.

Stub behavior can be split into at least three modes (examples):

- **constant baseline**: fix to neutral values (e.g., z-score=0)
- **pass-through**: forward an input as-is (only where meaningful)
- **missing + fail-closed**: emit `NaN/null` and rely on downstream gating to converge to “risk-down / no-trade”

The key requirement is: ablation must not break the graph, and the execution boundary must remain safely fail-closed.

### 9.3 Ablation scope: node vs group vs subgraph

If a node is reused across downstream paths, a single-node ablation affects all consumers simultaneously.
That may be intended (fine), or it may motivate “I want to cut only one usage”.

Recommended priority:

1. **group/subgraph ablation**: define meaningful bundles via `ablation_group` first.
2. **node-level ablation**: restrict to leaf features/gates where isolated effect is clear.

### 9.4 Recording: align run_manifest / search_intensity

Ablations are “additional experiments”, so they must be recorded to align with overfitting controls and auditability:

- include an `ablation_spec` (targets/mode/baseline) in run_manifest
- reflect generated ablation variants in `search_intensity` (variants / run count)

---

## 10. Concepts likely to conflict with existing design (draft) and how to handle them

Common tensions when introducing distillation, and the default principle: “connect only through SSOT paths + fail-closed”.

- **Strategy alpha vs platform (`qmtl/`) boundary**: distillation is not “move strategies into qmtl/”; it elevates reusable nodes/templates only.
- **Determinism (NodeID/run_manifest) vs rapid iteration**: generate ablations via DAG rewrite and seal them as separate run_id/manifests (keep baseline code unchanged).
- **Data contamination (multi-stream / extra feeds)**: default to “exclude from distillation inputs / label non-distillable”; escalate to failure for higher-tier worlds as needed.
- **Policy-change governance**: when recommendations lead to policy changes, reuse Independent Validation (policy diff) and override re-review as-is.

---

## 11. “Wall-street-grade” evaluation automation (draft): Stage-gate to first-order decisions

In QMTL, “wall-street-grade” scope is not just “run backtests automatically”. It is closer to automatically judging, via a standardized pipeline and policy (stage gates):

1) whether results are **accounting-consistent** (integrity),  
2) whether they are **statistically robust** (not overfit),  
3) whether assumptions about **execution/risk are realistic** (tradability), and  
4) whether the strategy has **portfolio placement value** (overlap/correlation/risk budget).  

### 11.1 Realistic automation ceiling

- **Near 100% automatable**: integrity/reproducibility (accounting invariants, run_manifest-based reproduction, sanity checks), plus KPI measurement/decomposition.
- **Automatable up to quantitative decisioning**: WF scoring, DSR/PSR/PBO, bootstrap success probabilities (policy cutlines must be fixed).
- **80–90% automatable**: failure-mode triage (playbook tagging) + standard report generation/storage/ranking.
- **Final deployment sign-off** is usually kept: economic rationale/capacity/ops risk/regulatory constraints are hard to fully quantify.

### 11.2 Recommended stage-gate skeleton (draft)

Below is a minimal skeleton for “automatic evaluation and promotion recommendations”. It should align with `EvaluationRun.summary.status/recommended_stage` and WorldPolicy `validation_profiles`.

1. **Stage 0: Integrity Gate (PASS/FAIL)**
   - PnL accounting invariants (e.g., `daily_*` sums == `trades_*` sums), fee/friction recorded (not zero), determinism reproduction (same commit+dataset+manifest → same hash).
2. **Stage 1: DEV performance + friction sensitivity**
   - detect “friction dominates”, sample-starved/0-trade patterns, etc. (as triage outputs).
3. **Stage 2: WF robustness**
   - OOS sum, fold sign stability, worst-fold, OOS/IS ratio + overfitting controls (DSR/PSR, optional PBO/CSCV, bootstrap probability KPIs).
4. **Stage 3: Stress (slippage/fees/regime)**
   - conservative execution stress (+bps, spread widening) and regime fragility evaluation.
5. **Stage 4: Paper-forward (real-time simulation)**
   - validate drift/execution gaps under live-like conditions (ops/monitoring automation becomes the focus).
6. **Stage 5: Pilot (small capital / low leverage)**
   - automated monitoring + kill switches + reporting; “automatic capital deployment” is typically gated by two-key approvals.

### 11.3 Stage-gate policy template (sketch)

This is a sketch to explain structure. The real fields/DSL must be synchronized with WorldPolicy/ValidationRule implementations; before stabilization, introduce only as additive extensions (e.g., via `diagnostics.extra_metrics`).

```yaml
# (sketch) config/worlds/<world_id>.yml
stage_gates:
  stage0_integrity:
    blocking:
      - invariants.pnlsums == true
      - invariants.fee_nonzero == true
      - determinism.repro_hash_match == true
  stage1_dev:
    blocking:
      - perf.net_sharpe >= 0.3
      - triage.friction_dominates == false
    watch:
      - triage.sample_starved == true
  stage2_wf:
    blocking:
      - wf.oos_sum_pnl > 0
      - robustness.dsr >= 0.15
    watch:
      - robustness.pbo > 0.2
  stage3_stress:
    blocking:
      - stress.slippage_bps_2.net_sharpe >= 0.0
    watch:
      - regime.fragile == true
  stage4_paper_forward:
    governance: manual_approval
  stage5_pilot:
    governance: two_key
```

### 11.4 Standard reports/artifacts (required fields) sketch

To make stage-gates operationally real, outputs must be locked not only as human-readable Markdown, but also as **machine-readable JSON**.

Required artifacts (examples):

- `run_manifest.json` (sealed inputs)
- `evaluation_run.json` (WS SSOT)
- `evaluation_report.json` (standard report including gates/triage)
- `evaluation_report.md` (human summary)

Minimal `evaluation_report.json` shape (sketch):

```json
{
  "meta": {
    "world_id": "crypto_mom_1h",
    "strategy_id": "abcd",
    "run_id": "7a1b4c...",
    "stage": "backtest|paper|live",
    "commit_sha": "…",
    "data_preset": "ohlcv.binance.spot.1m",
    "dataset_fingerprint": "…",
    "as_of": "2025-12-30T00:00:00Z"
  },
  "integrity": {
    "status": "pass|fail",
    "invariants": {"pnl_sums_match": true, "fee_nonzero": true},
    "notes": []
  },
  "metrics": {
    "returns": {},
    "sample": {},
    "risk": {},
    "robustness": {},
    "diagnostics": {}
  },
  "stress": {"scenarios": []},
  "portfolio_fit": {"correlation": {}, "marginal_var_es": {}},
  "triage": {"tags": ["friction_dominates"], "reason": "…"},
  "stage_gate": {"stage": "stage2_wf", "status": "pass|watch|fail", "reasons": []}
}
```

---

{{ nav_links() }}
