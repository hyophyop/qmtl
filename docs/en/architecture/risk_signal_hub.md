---
title: "Risk Signal Hub — Portfolio/Risk Snapshot SSOT"
tags: [architecture, risk, hub, world]
author: "QMTL Team"
last_modified: 2025-12-10
---

{{ nav_links() }}

# Risk Signal Hub — Portfolio/Risk Snapshot SSOT

!!! abstract "Role"
    Collect and normalize portfolio/risk snapshots (weights, covariance_ref/matrix, stress, realized returns) produced by Gateway and store them as a **single source of truth**.  
    WorldService, Exit Engine, and monitoring consumers read from the hub API/events to compute Var/ES, stress, and exit signals, and to monitor freshness/missing data.

Related documents:
- Archive (initial design): [archive/risk_signal_hub.md](../archive/risk_signal_hub.md)
- Operations runbook: [operations/risk_signal_hub_runbook.md](../operations/risk_signal_hub_runbook.md)

---

## 1. System Boundary and Flow

```mermaid
flowchart LR
    GW[Gateway\n(rebalance/fill producers)] -->|HTTP POST /risk-hub| HUB[(Risk Signal Hub\nWS router + Storage)]
    HUB -->|PortfolioSnapshotUpdated\nControlBus event| WS[WorldService\n(ExtendedValidation / Stress / Live workers)]
    HUB --> EXIT[Exit Engine\n(future)]
    HUB --> MON[Monitoring/Dashboards]
```

- **Producers**: Gateway rebalance/fill paths POST snapshots into the hub; large covariance payloads can be offloaded as refs.
- **Consumers**: WS ExtendedValidation/stress/live workers use hub lookups/events to compute Var/ES and stress. Exit Engine can subscribe to hub events to emit additional exit signals.
- **Events**: `PortfolioSnapshotUpdated` on ControlBus triggers workers/monitoring downstream.

---

## 2. Config/Deployment Profiles

- **dev**: Inline + fakeredis/in-memory cache only (covariance offload disabled). No persistent blob/file/S3 in dev; focus on functionality/minimal verification.
- **prod**: Postgres `risk_snapshots` + Redis cache; optional S3/Redis blob offload. ControlBus events required.
- The `risk_hub` block in `qmtl.yml` injects the same token/inline thresholds/blob store config into both Gateway (producer) and WS (consumer) to avoid drift.

---

## 3. Data Contract (Summary)

- Required: `world_id`, `as_of` (ISO), `version`, `weights` (sum≈1.0)
- Optional: `covariance` (inline when small) or `covariance_ref`, `realized_returns_ref`, `stress`, `constraints`, `ttl_sec`, `provenance`, `hash`
- Validation: weight sum > 0 and within 1.0±1e-3, ISO `as_of`, TTL expiration excludes stale snapshots from cache/lookups.

### 3.1 v1 Contract Defaults

- `X-Actor` and `X-Stage` headers are required and stored as `provenance.actor/stage`.
- TTL default: `ttl_sec=900` (15m). Max: `ttl_sec <= 86400` (422 otherwise).
- Version collisions: `(world_id, version)` collisions are rejected with **409** (no overwrite).
  - Idempotent retries (same `hash`) are treated as success and counted in `risk_hub_snapshot_dedupe_total`.
- API:
  - `POST /risk-hub/worlds/{world_id}/snapshots` (write; token/headers required)
  - `GET /risk-hub/worlds/{world_id}/snapshots/latest`
  - `GET /risk-hub/worlds/{world_id}/snapshots` (list)
  - `GET /risk-hub/worlds/{world_id}/snapshots/lookup?version=...|as_of=...`

---

## 4. Storage and Cache

- **Meta/versions**: Postgres/SQLite (`risk_snapshots`) with indexes on `(world_id, as_of/version)`.
- **Cache**: Redis (or fakeredis in dev) for latest snapshot hot path.
- **Blob offload**: Redis/S3 in prod only; dev keeps everything inline. Gateway and WS share `inline_cov_threshold`.

---

## 5. Security and Operations

- Auth: Hub router bearer token (`risk_hub.token`) shared only with Gateway producers.
- Observability: `risk_hub_snapshot_lag_seconds`, `risk_hub_snapshot_missing_total` metrics and Alertmanager rules (RiskHubSnapshotStale/Missing).
- Background workers: ControlBus consumer example `scripts/risk_hub_worker.py`; health checker `scripts/risk_hub_monitor.py`.

---

## 6. Future Extensions

- Exit Engine: derive and emit additional exit signals from hub events.
- Stress/live re-simulation: schedule via hub events → queue/ControlBus workers.
- Standardize large returns/covariance refs and retention policies (prod only).

{{ nav_links() }}
