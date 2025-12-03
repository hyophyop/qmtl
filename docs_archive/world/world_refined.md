# World Design Review and Refinements (Research Summary, archived)

> Archived research draft. Current world spec: `docs/world/world.md`.

This note critically reviews the initial research draft for Worlds and
consolidates actionable refinements across semantics, policy DSL, transition
safety, risk budgeting, shared resources, observability, and work items.

## 1) Fit and Gaps

What works
- QMTL already supports PaperTrading ↔ Brokerage switching, Runner orchestration,
  performance metrics (Sharpe, MDD), and Prometheus integration, so a
  “validate → promote” pipeline integrates naturally.
- Binding policy/resources/observability at world boundaries is appropriate.

Gaps
1. Time/data semantics
   - Define data currency explicitly (now − data_end tolerance) to prevent
     look‑ahead/survivorship bias on backfill catch‑up.
2. Sample sufficiency/statistical validity
   - Add minimum sample days, trade counts, confidence thresholds, and
     guardrails to mitigate overfitting.
3. Transition atomicity/safety
   - Enforce 2‑phase semantics (drain, idempotency, rollback, double‑order
     prevention) for dry‑run → live.
4. Portfolio/risk budgets
   - Pairwise correlation alone is insufficient. Add VAR/gross/net/sector caps,
     leverage bounds, and circuit breakers.
5. Multi‑world and shared nodes
   - If introducing shared nodes, enforce strict boundaries (hash namespaces),
     and drain safely during pruning.
6. Observability and governance
   - Standardize audit logs, version rollback, SLOs, and alert rules.

## 2) Refined Design (Highlights)

A. Data Currency Gate
- `max_lag`, `min_history`, `bar_alignment`, per‑metric warmup.
- Decide initial phase by comparing `now - data_end` with `max_lag`.

B. Policy DSL: Gate + Score + Constraint + Hysteresis
- Gates: thresholds and sufficiency.
- Score: bounded expressions.
- Constraints: correlation/exposure, sector caps, leverage.
- Hysteresis: promote/demote after K passes, min dwell.

Example
```yaml
selection:
  gates:
    and: [sharpe_mid >= 0.60, trades_60d >= 40, max_dd_120d <= 0.25, sample_days >= 30]
  score: "sharpe_mid + 0.1*winrate_long - 0.2*ulcer_mid"
  topk: { total: 8, by_side: { long: 5, short: 3 } }
  correlation: { max_pairwise: 0.8 }
  exposure:
    gross_budget: { long: 0.60, short: 0.40 }
    max_leverage: 3.0
```

## 3) Work Items (Condensed)

- Domain/store: world/policy schemas; audit/decision logs.
- Policy/eval: DSL parser + validator; sufficiency and currency gates; evaluator.
- Execution/transition: `OrderGateNode`; 2‑phase applier; position policies.
- Multi‑world/resources: SILO by default; shared nodes optional with namespaces.
- Observability: SLOs and alerts for promotion/demotion/failure/latency.
- CLI/API: evaluation/apply endpoints and world‑scoped RBAC.

## 4) Parameter Separation

- Side‑specific budgets and Top‑K (e.g., `gross_budget: { long: 60%, short: 40% }`).
- Manage StrategyInstance(params) per world/side for clarity and auditability.

## 5) Expected Outcomes

- Positive: policy/resource/observability separation; measurable, auditable
  promotions; safe automation.
- Neutral: complexity increases with shared nodes—mitigate via staged adoption.
- Negative: without drain/hysteresis/risk cuts, toggling and unintended orders
  may occur—default policies should remain conservative.
