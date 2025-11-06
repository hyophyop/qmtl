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
  - `scaling` (default), `overlay`, or `hybrid` (both)

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

Response extension
- `overlay_deltas`: proxy instrument deltas sized for overlay mode
- Scaling results remain in `per_world` and `global_deltas`

Gateway execution
- `POST /rebalancing/execute` honors `mode` and `shared_account`:
  - Scaling (default): `orders_per_world`
  - Shared-account netting: `orders_global` (global_deltas)
  - Overlay/hybrid: `orders_global` (overlay_deltas)

Pluggability
- WorldService chooses an engine per mode.
  - Scaling: `MultiWorldProportionalRebalancer`
  - Overlay: `OverlayPlanner`
  - Hybrid: both
- API schemas stay stable, enabling module replacement or call-time selection.

{{ nav_links() }}

