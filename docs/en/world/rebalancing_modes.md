---
title: "Rebalancing Modes: Scaling vs Overlay"
tags: [world, rebalancing]
last_modified: 2026-03-06
---

# Rebalancing Modes: Scaling vs Overlay

Definitions
- Scaling: Multiply each strategy sleeve’s per-symbol target vector by a scalar; preserve relative structure.
- Overlay: Do not touch underlying positions; use a top-level proxy (index futures/ETF/perp) to offset/add exposure to reach targets.

Differences
- Scaling: precise alignment (low TE), higher trade count/cost, subject to symbol constraints
- Overlay: minimal alpha interference and cost, higher basis/funding/margin risks

Selecting in QMTL
- Set `mode` in `POST /rebalancing/plan|apply`.
  - `scaling` (default)
  - `overlay` (uses overlay instruments to scale world notional; see below)
  - `hybrid` (not implemented — returns HTTP 501)

Overlay request extension
```json
{
  "mode": "overlay",
  "overlay": {
    "instrument_by_world": {"a": "ES_PERP", "c": "BTCUSDT_PERP"},
    "price_by_symbol": {"ES_PERP": 5000.0, "BTCUSDT_PERP": 60000.0},
    "min_order_notional": 50.0
  }
}
```

Status
- Overlay is supported when `overlay.instrument_by_world` and `overlay.price_by_symbol` are provided. Requests missing config return HTTP 422. Hybrid remains disabled and returns HTTP 501.

Gateway execution
- `POST /rebalancing/execute` honors `mode` and `shared_account`.
- Overlay plans expose `overlay_deltas`, and the Gateway maps them back into executable per-world orders while preserving `overlay_deltas` for inspection.
- Overlay execution assumes `overlay.instrument_by_world` maps each execution symbol to a single world. Duplicate overlay symbols across worlds are rejected with HTTP 422 on the Gateway execution surface.
- Hybrid remains unavailable and returns HTTP 501 on the public execution surface.

Pluggability
- Scaling engine is active (`MultiWorldProportionalRebalancer`).
- Overlay planner is active when configured; Hybrid is still disabled until its design is complete.

!!! note "Core Loop scope"
    From the Core Loop P0/P1 perspective, **scaling is the paved-road mode**. Overlay/hybrid remain advanced options for world-level rebalancing.  
    Overlay should only be used in environments that have the necessary configuration and risk model; hybrid is explicitly blocked with HTTP 501 and sits outside the current roadmap scope.

{{ nav_links() }}
