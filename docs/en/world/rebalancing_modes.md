---
title: "Rebalancing Modes: Scaling vs Overlay"
tags: [world, rebalancing]
last_modified: 2025-11-04
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
- `POST /rebalancing/execute` honors `mode` and `shared_account`. Overlay plans include `overlay_deltas` (per-world overlay trades). Hybrid is not implemented and raises HTTP 501.

Pluggability
- Scaling engine is active (`MultiWorldProportionalRebalancer`).
- Overlay planner is active when configured; Hybrid is still disabled until its design is complete.

{{ nav_links() }}
