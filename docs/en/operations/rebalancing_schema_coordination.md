---
title: "WS↔Gateway↔SDK Rebalancing Coordination Checklist"
tags: ["coordination", "rebalancing"]
author: "QMTL Team"
last_modified: 2025-11-13
---

{{ nav_links() }}

# WS↔Gateway↔SDK Rebalancing Coordination Checklist

This document tracks issue #1514 “Coordination: WS↔Gateway schema + SDK alpha metrics.” Use it to ensure the WorldService (#1513), Gateway/DAG (#1512), and SDK runtime (#1511) branches land in sync before merging.

## Context

- MultiWorldRebalanceRequest/Plan moves from v1 (scaling mode only) to v2 (overlay/hybrid ready, `alpha_metrics` attached).
- The `alpha_performance` metric keys/units must match across SDK ↔ Gateway ↔ WorldService.
- If these gates land asynchronously, Gateway may fail to parse WorldService responses or the SDK may mis-handle new metrics.

## Milestone checklist

### 1. WorldService (schema/gate/docs)

- [ ] Add `schema_version` to `MultiWorldRebalanceRequest` / `RebalancePlanModel` with a default of `1`.
- [ ] Introduce v2-gated `alpha_metrics` (per_world/per_strategy) and `rebalance_intent.meta`, stripping them when serving v1 clients.
- [ ] Ensure the `alpha_metrics` envelope uses the `alpha_performance.<metric>` namespace (e.g., `alpha_performance.sharpe`, `alpha_performance.max_drawdown`) and defaults each value to `0.0` when actual history isn’t provided, keeping downstream parsers simple.
- [ ] Add `WorldServiceConfig.compat_rebalance_v2` and surface the current version/flag in `/rebalancing/plan|apply` responses and ControlBus events.
- [ ] Wire the new `worldservice.server.compat_rebalance_v2` and `worldservice.server.alpha_metrics_required` settings into `create_app()` so operators can toggle v2 support (or require it) per deployment.
- [ ] Update `docs/en|ko/architecture/worldservice.md` and `docs/en|ko/world/rebalancing.md`, linking back to this checklist.
- [ ] Tests: `uv run -m pytest -W error -n auto qmtl/services/worldservice/tests` with v1/v2 fixtures.

### 2. Gateway/DAG (compat flag + contracts)

- [ ] Drive the new capability bits via config: set `gateway.rebalance_schema_version` (default `1`) and `gateway.alpha_metrics_capable` (default `false`) only after SDK/WS are v2-ready. Optionally publish a `gateway.compute_context_contract` string for SDK discovery.
- [ ] Extend Gateway health + `/rebalancing/execute` responses with `rebalance_schema_version` and `alpha_metrics_capable`.
- [ ] Teach `WorldServiceClient.post_rebalance_plan` to negotiate versions (prefer v2, fall back to v1) and cover it with JSON contract tests.
- [ ] Add dual v1/v2 fixtures for `/rebalancing/execute` and ControlBus fan-out tests (e.g., `tests/services/gateway/test_rebalancing_execute_contract.py`).
- [ ] Wire these tests into the Gateway/DAG Radon plan (#1512) regression suite.

### 3. SDK runtime (parser/docs/metrics)

- [ ] Emit `alpha_performance.<metric>` keys and make the parser ignore unknown keys by default.
- [ ] Consume the Gateway health `alpha_metrics_capable` bit to toggle SDK feature flags safely.
- [ ] Document the new metric keys/units in `docs/en|ko/guides/sdk_tutorial.md` and `docs/en|ko/reference/report_cli.md`.
- [ ] Tests: `uv run -m pytest -W error -n auto qmtl/runtime/tests qmtl/runtime/sdk/tests` plus the timeout preflight.

### 4. Shared outcomes

- [ ] Maintain a shared checklist (this document or a synced spreadsheet) and mark all boxes ✅ before enabling schema v2.
- [ ] Dry-run the flow Gateway health → SDK runtime call → WorldService `/rebalancing/plan` with `schema_version=2`.
- [ ] Merge order: #1512 → #1511 → #1513, then merge the checklist PR with `Fixes #1514`.

## Verification commands

```bash
# Health & compatibility
uv run --with httpx python scripts/check_gateway_health.py --expect-schema-version 2
# Docs
uv run mkdocs build
# Tests
PYTHONFAULTHANDLER=1 uv run --with pytest-timeout -m pytest -q --timeout=60 --timeout-method=thread --maxfail=1
uv run -m pytest -W error -n auto qmtl/services/worldservice/tests qmtl/services/gateway/tests qmtl/runtime/sdk/tests
```

Once every item above is satisfied, include `Fixes #1514` in the final PR body to auto-close the coordination issue.
