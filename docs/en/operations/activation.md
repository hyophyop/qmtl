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

## WS SSOT & client surfaces
- WorldService activation/evaluation is the single source of truth (SSOT) for `status/weight/contribution`. CLI/SDK submit surfaces WS output directly.
- Local ValidationPipeline output is shown separately as “pre-check” (non-authoritative) for debugging; investigate WS metrics/logs first when there is a mismatch.
- Downgrade signals (`downgraded/safe_mode/downgrade_reason`) remain at the top-level to expose default-safe paths from CLI/SDK.

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
- Use world-scoped metrics such as `pretrade_attempts_total{world_id="demo"}` to verify activation state per world.

{{ nav_links() }}
