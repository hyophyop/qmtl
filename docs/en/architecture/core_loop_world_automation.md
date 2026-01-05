---
title: "Core Loop × WorldService — Campaign Automation and Promotion Governance"
tags: [architecture, core-loop, worldservice, campaign, governance]
author: "QMTL Team"
last_modified: 2025-12-15
---

{{ nav_links() }}

# Core Loop × WorldService — Campaign Automation and Promotion Governance

!!! abstract "Summary"
    The Core Loop converges on “submit strategy + world, then the world manages stages (backtest → paper(dryrun) → live)”.  
    Callers use `Runner.submit(strategy, world=...)` only; stage/promotion/governance is decided by **WorldService policy**.  
    Evaluation inputs (especially realized returns and portfolio snapshots) are anchored to the `risk_signal_hub` SSOT.

Related documents:
- System blueprint: [architecture/architecture.md](architecture.md)
- WorldService: [architecture/worldservice.md](worldservice.md)
- Risk Signal Hub: [architecture/risk_signal_hub.md](risk_signal_hub.md)
- Evaluation runs & metrics API (icebox, reference-only): [design/worldservice_evaluation_runs_and_metrics_api.md](../design/icebox/worldservice_evaluation_runs_and_metrics_api.md)
- Strategy/node distillation (icebox, reference-only): [design/strategy_distillation.md](../design/icebox/strategy_distillation.md)
- (Archive) Step-by-step roadmap: [archive/core_loop_world_roadmap.md](../archive/core_loop_world_roadmap.md)

---

## 1. System boundary and flow

```mermaid
flowchart LR
    U[User/CI] -->|Runner.submit(strategy, world)| SDK[SDK/Runner]
    SDK -->|submit payload| GW[Gateway]
    GW -->|/worlds/{id}/evaluate\n/activation\n/apply| WS[WorldService]
    GW -->|POST /risk-hub| HUB[(Risk Signal Hub)]
    HUB -->|risk_snapshot_updated\nControlBus event| WS
    SCHED[Scheduler/Loop\n(qmtl or external)] -->|POST /worlds/{id}/campaign/tick\n(+ execute recommended actions)| WS
```

- **Runner/SDK**: user-facing submission surface (`Runner.submit(strategy, world=...)`).
- **WorldService**: world-policy SSOT; owns evaluation runs, campaign state, promotion candidates, and governance decisions.
- **Risk Signal Hub**: portfolio/risk/realized-return snapshot SSOT. It is “storage-only”; producers own computation.
- **Scheduler/Loop**: lightweight orchestration (Phase 4). External schedulers or `qmtl world campaign-loop` consume `tick` and execute recommended actions.

---

## 2. Core Loop contract (SSOT)

- **No client-side `mode`.**
  - Stages and promotions are decided by world policy + WS.
  - SDK/Runner treat WS decision envelopes as input only.
- **Default-safe**:
  - When WS decisions are missing or stale, downgrade to compute-only (backtest).
  - With `allow_live=false`, live transitions (activation/apply) are never permitted.

---

## 3. Evaluation runs and metric sourcing (Phase 2–4 core)

WorldService tracks “submit/evaluate/validate/promotion-candidate” via **Evaluation Runs**.

- Evaluation endpoints (conceptually):
  - `POST /worlds/{id}/evaluate` (single strategy)
  - `POST /worlds/{id}/evaluate-cohort` (campaign/cohort)
- `run_id` is the idempotency/replay identifier (re-running should update the same run).
- **Clients do not need to assemble metrics.**
  - If request `metrics` is empty, WS fills it via sourcing before evaluation.
  - Priority (summary):
    - reuse latest evaluation-run metrics (prefer same stage) →
    - enrich from `risk_signal_hub` snapshots (covariance/stress/realized returns ref/inline) →
    - (paper/live/shadow/dryrun) if `realized_returns` exists, derive v1 core performance metrics from the return series

!!! note "Time-based metric refresh via `realized_returns`"
    Without external engines, periodic `/evaluate` calls are enough to refresh paper/live metrics (sharpe/max_drawdown/effective_history_years, etc.).  
    Producers (e.g., Gateway) still own the responsibility of producing/aggregating the returns series.

---

## 4. Campaign orchestration (Phase 4)

Campaigns are “loops that fill observation windows and compute promotion candidates”.

- Policy (summary):
  - Encode minimum observation windows and sample constraints via fields like `campaign.backtest.window` and `campaign.paper.window`.
- State (summary):
  - `phase: backtest_campaign | paper_campaign | live_campaign`
  - Expose per-phase progress, observed key metrics, and promotion eligibility reasons.
- `tick` (lightweight contract):
  - `POST /worlds/{id}/campaign/tick` returns “recommended next actions” with **no side effects**.
  - Actions include `idempotency_key`, `suggested_run_id`, and `suggested_body` templates (do not include metrics).

---

## 5. Live promotion governance (Phase 5)

Live promotion is primarily an operator/governance step, fixed per world policy.

- Policy example:
  - `governance.live_promotion.mode: disabled | manual_approval | auto_apply`
- Invariant:
  - Even with `auto_apply`, paper(dryrun) observation and validation gates are **not skipped**.
- Fail-closed (required):
  - If the `risk_signal_hub` snapshot is missing/expired/stale, promotion is blocked and the blocking reason is recorded.
