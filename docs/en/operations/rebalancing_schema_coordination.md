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

## Status snapshot (2025-11-13)

- **#1513 – WorldService:** `schema_version` negotiation, the `alpha_metrics` envelope, and the new v2-only `rebalance_intent.meta` echo now ship together, and the ControlBus `rebalancing_planned` events mirror the same metadata with v1/v2 contract tests in place (`qmtl/services/worldservice/schemas.py#L248-L281`, `qmtl/services/worldservice/routers/rebalancing.py#L55-L219`, `qmtl/services/worldservice/controlbus_producer.py#L23-L109`, `tests/qmtl/services/worldservice/test_worldservice_api.py#L322-L480`).
- **#1512 – Gateway/DAG:** Config + health/reporting expose the capability bits; `WorldServiceClient.post_rebalance_plan` prefers the configured schema version with a 400/422 fallback, and both the execute route and ControlBus consumer have regression coverage (see `qmtl/services/gateway/world_client.py#L382-L430`, `qmtl/services/gateway/routes/rebalancing.py#L34-L160`, `tests/qmtl/services/gateway/test_rebalancing_route.py#L100-L174`, `tests/qmtl/services/gateway/test_controlbus_consumer.py#L252-L403`). Dedicated `/rebalancing/execute` dual-contract fixtures tied into the Radon plan are still pending.
- **#1511 – SDK runtime:** Parser + docs + health-bit consumption landed earlier, and the `alpha_performance` transforms now emit the `alpha_performance.<metric>` namespace with Runner + CLI/backtest coverage (`qmtl/runtime/transforms/alpha_performance.py#L124-L178`, `qmtl/runtime/sdk/runner.py#L667-L687`, `tests/qmtl/interfaces/cli/test_report_cli.py#L8-L21`, `tests/qmtl/runtime/sdk/test_backtest_contracts.py#L135-L155`). Full timeout preflight + suite execution is still pending.
- **Test sampling (2025-11-13):** `uv run -m pytest -W error -n auto tests/qmtl/services/worldservice/test_worldservice_api.py tests/qmtl/services/gateway/test_rebalancing_route.py tests/qmtl/runtime/test_alpha_metrics.py tests/qmtl/runtime/sdk/test_runner_health.py` ✅; hang-preflight plus the full gateway/runtime suites still need to run before flipping the final switches.

## Milestone checklist

### 1. WorldService (schema/gate/docs)

- [x] Add `schema_version` to `MultiWorldRebalanceRequest` / `RebalancePlanModel` with a default of `1` (implemented in `qmtl/services/worldservice/schemas.py:253-274` and enforced in `qmtl/services/worldservice/routers/rebalancing.py:54-187`; covered by `tests/qmtl/services/worldservice/test_worldservice_api.py:242-355`).
- [x] Introduce v2-gated `alpha_metrics` (per_world/per_strategy) and `rebalance_intent.meta`, stripping them when serving v1 clients (v2 responses now echo intent metadata while v1 responses omit it; see `qmtl/services/worldservice/schemas.py:248-281`, `qmtl/services/worldservice/routers/rebalancing.py:70-219`, `tests/qmtl/services/worldservice/test_worldservice_api.py:322-480`).
- [x] Ensure the `alpha_metrics` envelope uses the `alpha_performance.<metric>` namespace and defaults each value to `0.0` (`qmtl/services/worldservice/alpha_metrics.py:1-84`; verified in `tests/qmtl/services/worldservice/test_worldservice_api.py:314-319`).
- [x] Add `WorldServiceConfig.compat_rebalance_v2` and surface the current version/flag in `/rebalancing/plan|apply` responses and ControlBus events (`qmtl/services/worldservice/config.py:25-110`, `qmtl/services/worldservice/api.py:96-210`, `qmtl/services/worldservice/controlbus_producer.py:23-109`).
- [x] Wire the new `worldservice.server.compat_rebalance_v2` and `worldservice.server.alpha_metrics_required` settings into `create_app()` so operators can toggle v2 support (or require it) per deployment (`qmtl/services/worldservice/api.py:96-210`, `qmtl/foundation/config.py:470-520`).
- [x] Update `docs/en|ko/architecture/worldservice.md` and `docs/en|ko/world/rebalancing.md`, linking back to this checklist (see `docs/en/world/rebalancing.md:70-90` and `docs/ko/world/rebalancing.md:70-90`).
- [ ] Tests: `uv run -m pytest -W error -n auto qmtl/services/worldservice/tests` with v1/v2 fixtures — the targeted contract tests above passed locally, but the hang-preflight and the remainder of `qmtl/services/worldservice/tests` still need to run before merge.

### 2. Gateway/DAG (compat flag + contracts)

- [x] Drive the new capability bits via config: set `gateway.rebalance_schema_version` (default `1`) and `gateway.alpha_metrics_capable` (default `false`) only after SDK/WS are v2-ready. Optionally publish a `gateway.compute_context_contract` string for SDK discovery. (`qmtl/services/gateway/config.py:24-110`, `qmtl/foundation/config.py:470-520`, `qmtl/services/gateway/cli.py:137-195`.)
- [x] Extend Gateway health + `/rebalancing/execute` responses with `rebalance_schema_version` and `alpha_metrics_capable` (`qmtl/services/gateway/gateway_health.py:24-110`, `qmtl/services/gateway/routes/status.py:32-119`, `qmtl/services/gateway/routes/rebalancing.py:24-210`; exercised by `tests/qmtl/services/gateway/test_rebalancing_route.py:90-100`).
- [x] Teach `WorldServiceClient.post_rebalance_plan` to negotiate versions (prefer v2, fall back to v1) and cover it with JSON contract tests (`qmtl/services/gateway/world_client.py:382-430`, `tests/qmtl/services/gateway/test_world_client.py:48-105`, `tests/qmtl/services/gateway/test_rebalancing_route.py:100-174`).
- [x] Add dual v1/v2 fixtures for `/rebalancing/execute` and ControlBus fan-out tests — `tests/qmtl/services/gateway/test_rebalancing_execute_contract.py` now covers schema negotiation on the execute route and `tests/qmtl/services/gateway/test_controlbus_consumer.py` verifies the WebSocket relay for v2 metadata.
- [ ] Wire these tests into the Gateway/DAG Radon plan (#1512) regression suite — the plan PR still references the checklist but no regression job/assertions import the schema toggles yet.

### 3. SDK runtime (parser/docs/metrics)

- [x] Emit `alpha_performance.<metric>` keys and make the parser ignore unknown keys by default — `alpha_performance_node` now prefixes the canonical metrics and Runner/CLI/backtest tests cover the new shape (`qmtl/runtime/transforms/alpha_performance.py:124-178`, `qmtl/runtime/sdk/runner.py:667-687`, `tests/qmtl/interfaces/cli/test_report_cli.py:8-21`, `tests/qmtl/runtime/sdk/test_backtest_contracts.py:135-155`).
- [x] Consume the Gateway health `alpha_metrics_capable` bit to toggle SDK feature flags safely (`qmtl/runtime/sdk/runner.py:38-74`, `tests/qmtl/runtime/sdk/test_runner_health.py:9-22`).
- [x] Document the new metric keys/units in `docs/en|ko/guides/sdk_tutorial.md` and `docs/en|ko/reference/report_cli.md` (see `docs/en/guides/sdk_tutorial.md:270-300`, `docs/ko/guides/sdk_tutorial.md:228-250`, `docs/en/reference/report_cli.md:8-18`, `docs/ko/reference/report_cli.md:8-15`).
- [ ] Tests: `uv run -m pytest -W error -n auto qmtl/runtime/tests qmtl/runtime/sdk/tests` plus the timeout preflight — only the targeted subset noted above has run; full runtime + SDK suites (and the preflight timeout job) still need execution.

### 4. Shared outcomes

- [ ] Maintain a shared checklist (this document or a synced spreadsheet) and mark all boxes ✅ before enabling schema v2 — snapshot above reflects the latest review; remaining boxes stay unchecked until the open gaps are closed.
- [ ] Dry-run the flow Gateway health → SDK runtime call → WorldService `/rebalancing/plan` with `schema_version=2` (no rehearsal artifacts or logs yet).
- [ ] Merge order: #1512 → #1511 → #1513, then merge the checklist PR with `Fixes #1514` once the unchecked items move to ✅.

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
