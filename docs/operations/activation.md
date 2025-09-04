---
title: "World Activation Runbook — Freeze/Drain/Switch/Unfreeze"
tags: [operations, runbook, world]
author: "QMTL SRE"
last_modified: 2025-08-29
---

{{ nav_links() }}

# World Activation Runbook — Freeze/Drain/Switch/Unfreeze

## Scenarios
- Planned promotion/demotion
- Emergency circuit (disable all orders for a world)
- Rollback after failed apply

## Preconditions
- Confirm NTP health on WorldService and Gateway nodes
- Identify `world_id` and current `resource_version`/`etag`

## Procedures

1) Freeze/Drain
- PUT `/worlds/{id}/activation` with override `{ active:false }` (world‑wide) or add a circuit flag
- Verify orders gated OFF via SDK metrics/logs

2) Apply (Switch)
- POST `/worlds/{id}/evaluate` to generate a plan
- Review plan; POST `/worlds/{id}/apply` with `run_id`
- Monitor `world_apply_duration_ms` and audit log for completion

3) Unfreeze
- Remove circuit/override; verify ActivationEnvelope etag advanced

## Rollback
- If apply fails or regression is detected, restore previous activation snapshot (recorded in audit log)
- Confirm via `GET /worlds/{id}/activation` and SDK behavior

## Alerts & Dashboards
- Alerts: promotion_fail_total, activation_skew_seconds, stale_decision_cache
- Dashboards: world_decide_latency_ms_p95, event fanout lag, gateway proxy error rates

### World-specific Metrics Examples

When monitoring specific worlds, you can filter metrics by `world_id` label:

```promql
# Alpha performance for crypto world
alpha_sharpe{world_id="crypto_mom_1h"}
alpha_max_drawdown{world_id="crypto_mom_1h"}

# Pre-trade rejections by world and reason
pretrade_rejections_total{world_id="equity_trending", reason="position_limit"}
pretrade_rejection_ratio{world_id="fx_carry"}

# Node processing performance by world
rate(node_processed_total{world_id="crypto_mom_1h"}[5m])
histogram_quantile(0.95, node_process_duration_ms{world_id="crypto_mom_1h"})

# Cache read patterns by world
cache_read_total{world_id="equity_trending", upstream_id="binance_1min", interval="60"}
```

{{ nav_links() }}

