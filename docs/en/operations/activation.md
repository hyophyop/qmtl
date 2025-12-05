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

## Procedures (2‑Phase Apply)

1) Freeze/Drain
- PUT `/worlds/{id}/activation` with `{active:false}` or CLI:  
  `uv run qmtl world activation set <world> --active=false --reason maintenance --etag <etag>`
- Verify order gates OFF via SDK/Gateway metrics (`pretrade_attempts_total` drop)

2) Evaluate
- POST `/worlds/{id}/evaluate` or CLI: `uv run qmtl world eval <world> --output json --as-of ...`
- Capture `ttl/etag/run_id` from the response for apply input

3) Apply (Switch)
- POST `/worlds/{id}/apply` with `run_id` (required) and `etag` (optimistic lock)  
  CLI: `uv run qmtl world apply <world> --plan plan.json --run-id $(uuidgen) --etag <etag>`
- Monitor `world_apply_duration_ms`, `activation_skew_seconds`, and audit log entries (`world:<id>:activation`)

4) Unfreeze
- Remove overrides and confirm ActivationEnvelope `etag` increments/TTL is valid via `uv run qmtl world activation get <world>`

## Rollback
- On apply failure or regression, restore the previous activation snapshot from the audit log (`activation set`) and verify via SDK/CLI WS envelopes.
- Track until `promotion_fail_total` alerts clear.

## Alerts & Dashboards
- Alerts: `promotion_fail_total`, `activation_skew_seconds`, `stale_decision_cache`
- Dashboards: `world_decide_latency_ms_p95`, ControlBus fanout lag, Gateway proxy error rates
- World-scoped metrics (e.g., `pretrade_attempts_total{world_id="demo"}`) cross-check circuit state per world.

{{ nav_links() }}
