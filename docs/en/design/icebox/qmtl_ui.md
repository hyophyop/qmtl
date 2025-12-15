# QMTL UI Design

!!! warning "Icebox (Reference-only)"
    This document lives under `docs/en/design/icebox/` and is **not an active work item/SSOT**. Use it for background/reference only; promote adopted parts into `docs/en/architecture/` or code/tests.

## 0. Goals and Scope

- Define a UI layer that visualizes and operates the existing Gateway, DAG Manager, and WorldService paths. No new backend; add a thin UI/CLI skin on top of current components.
- Reuse the same configs/secrets (e.g., `config-cli`, environment variables) and start the UI via `qmtl ui` CLI for local/staging.
- Keep the flows consistent with [`architecture/architecture.md`](../../architecture/architecture.md), [`architecture/gateway.md`](../../architecture/gateway.md), and [`architecture/dag-manager.md`](../../architecture/dag-manager.md). Target users: strategy authors, runner/deployment owners, SRE/risk teams.

## 1. User journeys and feature pillars

- Strategy canvas & DAG builder: compose data sources → feature extraction (qmtl utils) → simulation/execution pipelines with versioning.
- Project/portfolio view: per-strategy state, recent runs, performance metrics (return, MDD, Sharpe, slippage, etc.), asset/exchange distribution.
- Experiment/backtest hub: parameter sweeps, A/B comparison, notes and artifacts (logs, result files), one-click reproduce.
- Runbook & scheduler: cron/event runs, retry/timeout policies, live DAG state stream (pending/running/succeeded/failed).
- Data sources & connections: exchange/API key health, rate-limit/quota dashboard, health checks and key-expiry alerts.
- Monitoring/alerts: metrics/order events/latency/error-rate alerts (email/webhook/Slack), rule-based risk guards (position/exposure/slippage caps).
- Risk & capital: real-time positions/orders/PnL, VaR/worst-case scenarios, drawdown alerts, stop-loss/trailing-stop policies.
- Deployment pipeline: staging→prod promotion, change summary (diff), rollback/roll-forward, environment variable/secret scope management.
- Auditability & collaboration: execution logs, input parameters, code/node versions, user action history; RBAC, share links, comments/approvals.
- Templates & examples: gallery of common strategy/node templates, quickstart wizard, inline docs/architecture diagrams.
- Performance/cost visibility: per-run resource usage, cost estimates, cache/reuse hit rate, anomaly detection for resource spikes.

## 2. UI/CLI architecture overview

- UI server acts as a thin BFF that reads Gateway HTTP/gRPC endpoints and ControlBus events, handling normalization and auth mapping only.
- Run/deploy/schedule requests delegate to DAG Manager, WorldService, and Runner paths; the UI aggregates state and log streams for presentation.
- `qmtl ui` CLI shares the same config files and offers separate dev/hot-reload and production modes.

```mermaid
flowchart LR
  CLI[qmtl ui CLI] --> UIServer[UI server/BFF]
  UIServer --> Gateway[Gateway]
  Gateway --> Dag[Dag Manager]
  Gateway --> World[WorldService]
  UIServer --> ControlBus[ControlBus events]
  subgraph UI
    Canvas[DAG canvas & experiment hub]
    Ops[Ops/monitoring/alerts]
    Risk[Risk & deployment]
  end
  UIServer --> Canvas
  UIServer --> Ops
  UIServer --> Risk
```

## 3. CLI entrypoints (`qmtl ui`)

- `qmtl ui init`: create a UI profile, wire Gateway/ControlBus endpoints and tokens, generate a local `.env.ui` stub.
- `qmtl ui up`: run the UI server in production mode (build static assets and serve), print host/port.
- `qmtl ui dev`: run in dev mode (hot reload, proxy to Gateway/ControlBus).
- `qmtl ui status`: show running UI processes/ports/target environment and health summaries.
- `qmtl ui open`: open the current profile URL in a browser (non-headless assumption).
- `qmtl ui stop`: stop the local UI process.
- `qmtl ui export --project <id>`: export a static report for a strategy/experiment (options: metrics only / include logs).
- All commands honor shared flags `--profile`, `--config`, `--env-file` to stay aligned with Runner/Backend configuration.

## 4. Screen modules and wiring rules

- Canvas & DAG builder: reuse node templates, input/output schema, and DAG Manager state/run IDs to guarantee reproducibility.
- Experiment/backtest hub: cache run parameters, TagQuery, and metric artifacts; re-run locks the same parameters/node versions.
- Runbook/scheduler: surface DAG Manager scheduling API with retry/SLA/timeout templates.
- Monitoring/alerts: subscribe to ControlBus events and Gateway diagnostics to stream state changes.
- Deploy/rollback: diff env-specific secrets/configs and gate execution behind approvals.

## 5. Data and metadata to collect

- Strategy/experiment meta: run IDs, NodeSet/Template versions, input parameters, presets/worlds used, log fingerprints.
- Risk/positions: periodic snapshots of positions, order history, slippage/rate-limit events from WorldService/Execution Nodes.
- Observability: latency, error rate, cache hit rate, and cost estimates aggregated and cached in the UI server (ControlBus-driven).

## 6. Operations and security

- AuthZ/AuthN: reuse Gateway auth; UI sessions rely on short-lived tokens plus RBAC-based view filtering.
- Audit log: emit UI actions (run/stop/promote/rollback/config change) to a dedicated stream (ControlBus or audit channel).
- Failure handling: if Gateway/DAG Manager/WorldService are degraded, the UI falls back to read-only mode and surfaces retry/alternate endpoints.

## 7. Out of scope and follow-ups

- Mobile UX, multi-tenancy, and external identity federation stay out of scope for this draft.
- Expand build/deploy pipeline, performance budgets, and accessibility checklist in dedicated follow-up docs.
