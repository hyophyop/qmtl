---
title: "Risk Signal Hub — Portfolio/Risk Snapshot SSOT"
tags: [architecture, risk, hub, world]
author: "QMTL Team"
last_modified: 2026-04-03
---

{{ nav_links() }}

# Risk Signal Hub — Portfolio/Risk Snapshot SSOT

!!! abstract "Role"
    Collect and normalize portfolio/risk snapshots (weights, covariance_ref/matrix, stress, realized returns) produced by Gateway and store them as a **single source of truth**.  
    WorldService, Exit Engine, and monitoring consumers read from the hub API/events to compute Var/ES, stress, and exit signals, and to monitor freshness/missing data.

Related documents:
- [Gateway](gateway.md)
- [WorldService](worldservice.md)
- Archive (initial design): [archive/risk_signal_hub.md](../archive/risk_signal_hub.md)
- Validation architecture (icebox, reference): [design/world_validation_architecture.md](../design/icebox/world_validation_architecture.md)
- Operations runbook: [operations/risk_signal_hub_runbook.md](../operations/risk_signal_hub_runbook.md)

---

## 1. System Boundary and Flow

```mermaid
flowchart LR
    GW[Gateway\n(rebalance/fill producers)] -->|HTTP POST /risk-hub| HUB[(Risk Signal Hub\nWS router + Storage)]
    HUB -->|risk_snapshot_updated\nControlBus event| WS[WorldService\n(ExtendedValidation / Stress / Live workers)]
    HUB --> EXIT[Exit Engine\n(future)]
    HUB --> MON[Monitoring/Dashboards]
```

- **Producers**: Gateway rebalance/fill paths POST snapshots into the hub; large covariance payloads can be offloaded as refs.
- **Consumers**: WS ExtendedValidation/stress/live workers use hub lookups/events to compute Var/ES and stress. Exit Engine can subscribe to hub events to emit additional exit signals.
- **Event routing**: publishing `risk_snapshot_updated` and triggering extended validation are owned by the adjacent Core Loop layer (`qmtl/services/worldservice/core_loop_hub.py`). Risk Signal Hub itself remains the snapshot storage/lookup SSOT.

---

## 2. Runtime and deployment boundary

- dev/prod storage profiles, tokens, blob-offload configuration, and freshness checks are managed operationally in the [Risk Signal Hub Runbook](../operations/risk_signal_hub_runbook.md).
- This document stays focused on what the hub standardizes and which services read and write it.

---

## 3. Data Contract (Summary)

- Required: `world_id`, `as_of` (ISO), `version`, `weights` (sum≈1.0)
- Optional: `covariance` (inline when small) or `covariance_ref`, `realized_returns` or `realized_returns_ref`, `stress`, `constraints`, `ttl_sec`, `provenance`, `hash`
- Validation: weight sum > 0 and within 1.0±1e-3, ISO `as_of`, TTL expiration excludes stale snapshots from cache/lookups.

### 3.1 v1 Contract

- `X-Actor` and `X-Stage` headers are required and stored as `provenance.actor/stage`.
- TTL default: `ttl_sec=900` (15m). Max: `ttl_sec <= 86400` (422 otherwise).
- Version collisions: `(world_id, version)` collisions are rejected with **409** (no overwrite).
  - Idempotent retries (same `hash`) are treated as success and counted in `risk_hub_snapshot_dedupe_total`.
- API:
  - `POST /risk-hub/worlds/{world_id}/snapshots` (write; token/headers required)
  - `GET /risk-hub/worlds/{world_id}/snapshots/latest[?stage=...&actor=...&expand=true]`
    - `stage`/`actor`: filter by `provenance.stage` / `provenance.actor`.
    - `expand=true`: resolves `covariance_ref` / `realized_returns_ref` / `stress_ref` when possible and returns inline fields (`covariance`, `realized_returns`, `stress`).
  - `GET /risk-hub/worlds/{world_id}/snapshots[?limit=...&stage=...&actor=...&expand=true]` (list)
  - `GET /risk-hub/worlds/{world_id}/snapshots/lookup?version=...|as_of=...`

### 3.2 `realized_returns` Contract (v1, storage-only)

`realized_returns` stores a “realized return time series” on the snapshot. The hub **does not compute/aggregate** `realized_returns`; producers (e.g., Gateway) compute it and the hub stores it. Core Loop v1 performance-metric derivation happens in the separate `core_loop_hub.py` layer.

- Recommended shape (per strategy):
  - `realized_returns: { "<strategy_id>": [r1, r2, ...], ... }`
- Value constraints:
  - Each element must be a **finite float**. (`NaN/±Inf` not allowed)
  - Empty series are not allowed (must contain at least 1 point).
- Ordering/semantics:
  - The array order is interpreted as “time order (oldest → newest)”.
  - Semantics such as return frequency (daily vs bar) and whether costs are included (net/gross) are a **producer contract** and should be fixed via `provenance` or operational docs.
- Size/transport:
  - Large payloads should be offloaded via `realized_returns_ref`, and consumers should request inline data via `expand=true`.

---

## 4. Storage and Cache

- **Meta/versions**: Postgres/SQLite (`risk_snapshots`) with indexes on `(world_id, as_of/version)`.
- **Cache**: Redis (or fakeredis in dev) for latest snapshot hot path.
- **Blob offload**: Redis/S3 in prod only; dev keeps everything inline. Gateway and WS share `inline_cov_threshold`.

---

## 5. Operational links

- Auth, token sharing, freshness alerts, and worker procedures are covered in the [Risk Signal Hub Runbook](../operations/risk_signal_hub_runbook.md).
- Global dashboards and alert routing live in [Monitoring and Alerting](../operations/monitoring.md) and [World Validation Observability](../operations/world_validation_observability.md).

---

## 6. Future Extensions

- Exit Engine: derive and emit additional exit signals from hub events.
- Stress/live re-simulation: schedule via hub events → queue/ControlBus workers.
- Standardize large returns/covariance refs and retention policies (prod only).

{{ nav_links() }}
