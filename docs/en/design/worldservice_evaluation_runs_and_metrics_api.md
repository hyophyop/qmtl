---
title: "WorldService Evaluation Runs & Metrics API Sketch"
tags: [design, worldservice, metrics, snapshot, pnl]
author: "QMTL Team"
last_modified: 2025-12-02
status: draft
related_issue: "hyophyop/qmtl#1750"
---

# WorldService Evaluation Runs & Metrics API Sketch

## 0. Motivation & Context

This document captures an initial design sketch for:

- letting WorldService **consume and expose PnL/metrics in a consistent, world-centric way** for gating,
- exposing **strategy lifecycle state** within a world (e.g., “backtest running”, “evaluated”, “activated”), and
- providing APIs to **fetch snapshots/metrics** once evaluation is complete,

from the perspective of the Core Loop and the external feedback in [hyophyop/qmtl#1750](https://github.com/hyophyop/qmtl/issues/1750).

Related docs:

- [Architecture](../architecture/architecture.md), [WorldService](../architecture/worldservice.md)
- [auto_returns unified design (Korean source)](../../ko/design/auto_returns_unified_design.md)
- [Core Loop Roadmap](core_loop_roadmap.md) *(Korean source remains canonical)*

All API shapes and schemas here are **draft-level**. They are meant to drive discussion; any implementation must be reconciled with existing worldservice/gateway/SDK contracts.

!!! note "Assumed responsibility split (where computations live)"
    - Strategy-level history replay, returns/metric computation, and (optionally) account-level PnL simulation are assumed to run in **Runner/SDK/ValidationPipeline**, not inside WorldService.
    - The APIs in this document treat WorldService as the component that **accepts already-computed metrics/PnL, applies world policies, and stores/exposes evaluation results and snapshots**.  
      (Rebuilding a full backtest/PnL engine inside WS is explicitly *out of scope* for this sketch.)

## 1. As‑Is / To‑Be Summary

### 1.1 As‑Is

- PnL/metrics:
  - ValidationPipeline and Runner compute returns and metrics today, but many projects reimplement their own returns→PnL→snapshot helpers.
  - WorldService can embed some metrics in its evaluation responses, but there is no explicit **“evaluation run” model + metrics API** yet.
- Strategy lifecycle:
  - `Runner.submit` orchestrates history warm-up, backtest, validation, and WS evaluate/apply, but
  - there is no explicit API or model to ask “where is this submission in the world lifecycle right now?”.
- Snapshots:
  - Each project invents its own `.qmtl_snapshots/*.json` format and logging utilities.

### 1.2 To‑Be (idea-level)

- WorldService introduces **Evaluation Runs** as a first-class concept:
  - Key: `(world_id, strategy_id, evaluation_run_id)`  
    (Here, `evaluation_run_id` lives in a **separate namespace** from any existing rebalancing/allocation run IDs.)
  - States: `submitted / backtest_running / evaluating / evaluated / activated / rejected / expired ...`
- Once an evaluation run completes:
  - WS stores a **standardised metric bundle** (returns/PnL summary, risk/performance metrics, gating reasons) and
  - exposes a **metrics/snapshot API** to retrieve it.
- Runner/CLI/tools:
  - receive an `evaluation_run_id` (or URL) from `Runner.submit`,
  - use a **status API** to see “where this run is in the lifecycle”, then
  - call the **snapshot API** to materialise metrics into JSON files when ready.
- Local PnL helpers:
  - become an **offline/preview** path that follows the same contract as WS metrics, rather than re-defining PnL semantics per project.

## 2. Strategy Lifecycle & Evaluation Run Model

### 2.1 Evaluation Run Concept

- Identifiers:
  - `world_id`: world ID
  - `strategy_id`: strategy ID (or `(strategy_id, version)` pair)
  - `run_id`: identifier for a specific submission/evaluation cycle

Evaluation run states are organised along two axes:
- **Computation scope:** per-strategy (replay/metric computation) vs world-level (policy/gating).
- **Time:** in-flight (running) vs fixed (evaluated and beyond).

- States (draft):
   - `submitted`: evaluation run registered by Runner/Gateway
   - `backtest_running`: history warm-up + replay backtest, **computing per-strategy returns/metrics**.
   - `evaluating`: metrics for this run are already available, and the WorldService policy engine is  
     **applying world-level rules (threshold/top-k/correlation/hysteresis, cross-strategy comparisons) to decide activation/weights/violations**.
   - `evaluated`: both metric computation and policy evaluation have completed and the **world-level decision + metrics snapshot** for this run is fixed.
   - `activated`: world activation/weights derived from this run have been applied and are reflected in execution/gating.
   - `rejected`: the run has been evaluated but not activated due to policy violations or insufficient contribution.
   - `expired`: the run has been superseded by newer runs or TTL and remains only as historical reference.

In table form:

| State              | Scope         | Description |
|--------------------|--------------|-------------|
| `submitted`        | shared       | Run has been created but not yet executed |
| `backtest_running` | **strategy** | History replay and per-strategy returns/metrics are being computed |
| `evaluating`       | **world**    | WS policy engine is turning metrics into activation/weights/violations (threshold/top-k/correlation/hysteresis, cross-strategy view) |
| `evaluated`        | world        | World-level decision + metrics snapshot for this run are fixed |
| `activated`        | world        | Decisions have been applied to the world’s activation/weights and affect execution/gating |
| `rejected`         | world        | Run did not satisfy activation criteria and was discarded |
| `expired`          | shared       | Run is no longer a live candidate (superseded/TTL) and remains only as historical context |

State transitions (sketch):

```mermaid
stateDiagram-v2
    [*] --> submitted
    submitted --> backtest_running
    backtest_running --> evaluating
    evaluating --> evaluated
    evaluated --> activated
    evaluated --> rejected
    activated --> expired
    rejected --> expired
```

!!! note "`backtest_running` / `evaluating` usage guidance"
    - In this definition, `backtest_running` covers **strategy-level history replay and returns/metric computation**,  
      while `evaluating` covers the **world-level policy application** that turns those metrics into activation/weights/violations.
    - In the current v2 implementation these phases form a **single synchronous pipeline**, but the state model itself distinguishes strategy-level and world-level concerns.
    - When world-level evaluation (e.g., cross-world correlation/risk) becomes asynchronous or significantly more expensive, services can introduce a `phase: backtest | evaluate` sub-field and surface `evaluating` explicitly where it adds value.

!!! note "Evaluation run immutability and re-evaluation"
    - Once an `evaluation_run_id` reaches `evaluated`, the associated metrics/gating result should be treated as **immutable**; updates are append-only in terms of history/audit.
    - To re-evaluate a strategy under different conditions or at a later time, create a **new evaluation run with a new `evaluation_run_id`** instead of overwriting the old run.
    - Activation/weights derived from an evaluation run may change over time (e.g., via apply/allocation flows), but the evaluation snapshot for a given `evaluation_run_id` is expected to remain stable.

### 2.2 Relation to Runner.submit (conceptual)

- When `Runner.submit(MyStrategy, world="alpha_world")` is called:
  - Gateway/WS create or enqueue an evaluation run `(world_id, strategy_id, run_id)`.
  - `SubmitResult` may expose at least:
    - `world_id`
    - `strategy_id`
    - `evaluation_run_id` (or `evaluation_run_url`)
    - optionally, a `snapshot_url` for when metrics are ready.

## 3. API Flow Sketch

This section outlines REST-style endpoints for evaluation run status, metrics, and snapshot retrieval. Names and schemas are **illustrative** and must be reconciled with worldservice/gateway specs.

### 3.1 Evaluation Run Status API (draft)

- Purpose: answer “where is this submission in the world lifecycle?”.

- Example endpoint:

```http
GET /worlds/{world_id}/strategies/{strategy_id}/runs/{run_id}
```

- Response (sketch):

```json
{
  "world_id": "alpha_world",
  "strategy_id": "beta_mkt_simple",
  "run_id": "2025-12-02T10:00:00Z-uuid",
  "status": "evaluated",
  "created_at": "2025-12-02T10:00:01Z",
  "updated_at": "2025-12-02T10:05:30Z",
  "effective_mode": "validate",
  "activation_state": "pending",
  "links": {
    "metrics": "/worlds/alpha_world/strategies/beta_mkt_simple/runs/2025-.../metrics",
    "snapshot": "/worlds/alpha_world/snapshots/alpha_world-beta_mkt_simple-2025-..."
  }
}
```

- Runner/CLI:
  - `SubmitResult.evaluation_run_url` points here, so tools can see status and discover metrics/snapshot URLs.
  - CLI may provide `qmtl world run-status --world alpha_world --strategy beta_mkt_simple --run latest`.

### 3.2 Metrics API (draft)

- Purpose: fetch the **world-level evaluation metrics that WS owns and serves as a canonical contract**.
  - In an initial implementation, Runner/ValidationPipeline compute metrics/PnL and pass them to WS, which then uses them as the basis for policy evaluation and storage.
  - Over time WS may compute or augment some metrics itself, but this endpoint remains the **SSOT for “world evaluation metrics”**.

- Example endpoint:

```http
GET /worlds/{world_id}/strategies/{strategy_id}/runs/{run_id}/metrics
```

- Response (sketch; to be aligned with existing WS schemas):

```json
{
  "world_id": "alpha_world",
  "strategy_id": "beta_mkt_simple",
  "run_id": "2025-12-02T10:00:00Z-uuid",
  "status": "evaluated",
  "evaluation": {
    "returns": {
      "sample_count": 1440,
      "window": "2025-12-01T00:00:00Z/2025-12-02T00:00:00Z",
      "source": "auto_returns",
      "sharpe": 1.8,
      "max_drawdown": -0.12,
      "volatility": 0.25,
      "win_rate": 0.54,
      "profit_factor": 1.7
    },
    "pnl": {
      "sample_count": 1440,
      "reference_currency": "USD",
      "pnl_total": 1234.5,
      "pnl_max_drawdown": -230.0,
      "pnl_equity_peak": 10234.0
    },
    "risk": {
      "turnover_proxy": 0.8,
      "exposure_bounds_ok": true,
      "concentration_warnings": []
    },
    "gating": {
      "verdict": "valid",
      "violations": [],
      "hysteresis": {
        "promote_after": 5,
        "demote_after": 3
      }
    }
  }
}
```

This shape can serve as the **canonical “world evaluation metrics snapshot”** format.

!!! note "Call timing and error semantics"
    - When calling `GET /runs/{run_id}/metrics`:
      - If the specified `evaluation_run_id` does not exist, the service SHOULD return `404 Not Found`.
      - If the run exists but is not yet in `evaluated` status, the service SHOULD return `409 Conflict` with a machine-readable code such as `"error": "E_RUN_NOT_EVALUATED"`.
    - Clients are expected to first query `/runs/{run_id}` for status and only call the metrics endpoint once `status=evaluated`.

### 3.3 Snapshot API (draft)

- Purpose: build on the §3.2 metrics response and expose a snapshot object that combines metrics with lightweight series information (or references) as a **delivery/storage-friendly envelope** in a standard JSON format.

- Example endpoint:

```http
GET /worlds/{world_id}/snapshots/{snapshot_id}
```

- Response (sketch):

```json
{
  "snapshot_id": "alpha_world-beta_mkt_simple-2025-12-02T10:00:00Z",
  "world_id": "alpha_world",
  "strategy_id": "beta_mkt_simple",
  "run_id": "2025-12-02T10:00:00Z-uuid",
  "created_at": "2025-12-02T10:05:30Z",
  "metrics": { "...": "..." },
  "series_heads": {
    "returns": [0.001, -0.0005, "..."],
    "equity": [10000.0, 10010.0, "..."],
    "pnl": [0.0, 10.0, "..."]
  },
  "meta": {
    "pnl_source": "account_simulated_from_signals",
    "auto_returns": true,
    "tags": ["beta-factory", "sandbox"]
  },
  "storage_refs": {
    "full_returns_series": "s3://.../returns.parquet",
    "full_pnl_series": "s3://.../pnl.parquet"
  }
}
```

Projects can then reuse this WS snapshot format directly when writing `.qmtl_snapshots/*.json`, instead of inventing their own.

!!! note "Metrics API vs snapshot API"
    - `/runs/{run_id}/metrics` is the **canonical evaluation contract (SSOT)** owned by WS; policy/gating, dashboards, and algorithmic consumers (e.g., rebalancing engines) should read from this surface.
    - `/snapshots/{snapshot_id}` is an envelope that adds **series heads, storage references, and meta** on top of the same evaluation result and is primarily aimed at CLI/tools/external analysis pipelines that work with `.qmtl_snapshots/*.json`.

!!! note "Relationship to existing `/worlds/{id}/evaluate` API"
    - In an initial rollout, `/worlds/{world_id}/strategies/{strategy_id}/runs/{run_id}/metrics` is expected to wrap the existing `/worlds/{world_id}/evaluate` behaviour (or the same policy engine) and expose the **same evaluation outcome in a normalised schema**.
    - Over time the `/runs/*` family can become the primary “submit strategy → create evaluation run → fetch evaluation result” surface, while `/evaluate` is narrowed to compatibility/batch use cases or a lower-level entry point to the same engine.

## 4. SDK/CLI Flow (draft)

The following sequence diagram sketches how Runner/CLI might use these APIs:

```mermaid
sequenceDiagram
    participant User
    participant SDK as Runner/SDK
    participant GW as Gateway
    participant WS as WorldService

    User->>SDK: Runner.submit(MyStrategy, world="alpha_world")
    SDK->>GW: POST /strategies (submit)
    GW->>WS: POST /worlds/{world}/strategies/{strategy}/runs
    WS-->>GW: 202 Accepted + run_id
    GW-->>SDK: 202 Ack + { evaluation_run_id, ... }
    SDK-->>User: SubmitResult(evaluation_run_id=..., links=...)

    User->>SDK: SDK.poll_evaluation(evaluation_run_id)
    SDK->>WS: GET /worlds/{world}/strategies/{strategy}/runs/{run}
    WS-->>SDK: status=evaluated + links.metrics/snapshot

    SDK->>WS: GET /worlds/{world}/strategies/{strategy}/runs/{run}/metrics
    WS-->>SDK: evaluation metrics

    SDK->>WS: GET /worlds/{world}/snapshots/{snapshot_id}
    WS-->>SDK: snapshot JSON
    SDK-->>User: (optional) write snapshot JSON to .qmtl_snapshots/...
```

Possible CLI surface (idea-level):

- `qmtl submit strategies.beta_factory.beta_mkt_simple:Strategy --world alpha_world --snapshot`
- `qmtl world run-status --world alpha_world --strategy beta_mkt_simple --run latest`
- `qmtl world snapshot --world alpha_world --strategy beta_mkt_simple --run latest --output .qmtl_snapshots/alpha_world-beta_mkt_simple-latest.json`

## 5. Relationship to Local PnL Helpers

Even with WS/gateway-based evaluation, **pure local development** (no WS/gateway running) still benefits from PnL helpers. In that mode:

- A helper like `qmtl.sdk.pnl.simulate_long_account_from_returns(...)`:
  - should follow the same contract and semantics as WS metrics as closely as possible, and
  - act as a **preview/offline** approximation rather than redefining PnL per project.
- Runner/ValidationPipeline:
  - can use auto_returns + local PnL helpers for fast feedback,
  - but docs should clearly state that **WorldService remains the official source of truth** for policy decisions and gating.

This document is intentionally exploratory. Before implementing any of it, we must:

- align it with existing worldservice schemas (DecisionEnvelope/ActivationEnvelope/EvalKey),
- integrate it cleanly with commit-log/ControlBus patterns, and
- design a backward-compatible rollout strategy.
