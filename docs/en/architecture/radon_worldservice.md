---
title: "WorldService/Alpha Radon Plan"
tags: ["radon", "worldservice", "alpha"]
author: "QMTL Team"
last_modified: 2025-11-13
---

{{ nav_links() }}

# WorldService/Alpha Radon Plan

WorldService receives rebalancing/activation requests from Gateway and exposes the canonical MultiWorldRebalanceRequest/Plan schema plus `alpha_performance` metrics to upper services. Complexity has accumulated across `qmtl/services/worldservice/*` (#1513), and landing a schema or metric change without guards risks diverging contracts with Gateway/SDK. This plan reduces those hotspots and enumerates the actions required to satisfy issue #1514.

## Findings

| Area | Path | Radon | Notes |
| --- | --- | --- | --- |
| Allocation API | `WorldService.upsert_allocations` {{ code_url('qmtl/services/worldservice/services.py#L146') }} | E (32) | Locking, context building, planning, bus publishes, and execution live together |
| Rebalance schema | `MultiWorldRebalanceRequest` {{ code_url('qmtl/services/worldservice/schemas.py#L248') }} | extensibility risk | No version flag; overlay/nightly options share the same model |
| Decision metrics | `augment_metrics_with_linearity` {{ code_url('qmtl/services/worldservice/decision.py#L19') }} | C (17) | Hard to extend with `alpha_performance`; NaN/default rules unclear |
| Activation events | `ActivationEventPublisher.upsert_activation` {{ code_url('qmtl/services/worldservice/activation.py#L22') }} | B (8) | Freeze/unfreeze, gating, and bus publishes interleaved |
| Config surface | `load_worldservice_server_config` {{ code_url('qmtl/services/worldservice/config.py#L41') }} | C (14) | CLI/server/tests need separate overrides |

## Goals

- Lower `upsert_allocations` to A/B by separating planning, storage, and execution
- Add **schema_version + feature flags** to MultiWorldRebalanceRequest/RebalancePlan and sync them with Gateway (#1512) and SDK (#1511)
- Treat WorldService as the canonical author of the `alpha_performance` metric contract (keys, units, NaN handling)
- Add dual contract tests (REST + ControlBus) and run `uv run -m pytest -W error -n auto qmtl/services/worldservice/tests`

## Refactor tracks

### 1. Allocation staging

- Split `upsert_allocations` into four async helpers (lock acquisition, context build, plan+persist, optional execution) that pass an `AllocationExecutionPlan` dataclass around.
- Inject storage/bus/executor interfaces so tests can provide fakes; keep the public method as orchestration only (target CC < 10).

### 2. MultiWorldRebalance schema versioning

- Add `schema_version: Literal[1,2]` to `MultiWorldRebalanceRequest`, `RebalancePlanModel`, and ControlBus payloads. Fields such as `mode`, `overlay`, and upcoming `alpha_metrics` become version-gated.
- Introduce `alpha_metrics` (per-world/per-strategy `alpha_performance` dictionaries) and `rebalance_intent` metadata to prepare for overlay/hybrid support.
- Surface feature flags via `WorldServiceConfig.compat_rebalance_v2` and ControlBus topic metadata; this satisfies issue #1514’s “WS schema note” item once Gateway health exposes the same bit.
- Expose deployment-level toggles through `worldservice.server.compat_rebalance_v2` (enables v2) and `worldservice.server.alpha_metrics_required` (rejects schema_version<2). Thread both through `create_app()` so API/tests can enable or mandate v2 deterministically.

### 3. Alpha metric pipeline

- Refactor `decision.augment_metrics_with_linearity` to accept pluggable calculators, emit values under the `alpha_performance.{metric}` namespace, and document defaulting rules (0.0 when missing).
- When ControlBus rebalancing events include `alpha_metrics`, forward them unchanged; when absent, emit an empty dict so downstream SDK parsers can safely ignore it.

### 4. Activation/config modularization

- Break `ActivationEventPublisher` into explicit commands for freeze/unfreeze/upsert; each command performs one side effect and logs clearly.
- Rebuild `load_worldservice_server_config` as a reusable factory so CLI, server, and pytest share the exact same logic; expose the `compat_rebalance_v2` and `alpha_metrics_required` switches here.

### 5. Tests & docs

- Author versioned contract tests for `/rebalancing/plan|apply` and ControlBus publish paths (JSON fixtures for v1 + v2).
- Run `uv run -m pytest -W error -n auto qmtl/services/worldservice/tests` plus the timeout preflight for hangs.
- Update `docs/en/architecture/worldservice.md`, `docs/en/world/rebalancing.md`, and `docs/en/guides/strategy_workflow.md` with the new schema and metric bindings; this plan remains the canonical reference.

## Timeline

| Phase | Duration | Deliverables |
| --- | --- | --- |
| Phase 1 | 2 days | Allocation staging + test doubles |
| Phase 2 | 3 days | Schema v2 definition, feature flags, REST/ControlBus contract coverage |
| Phase 3 | 2 days | Alpha metric docs/code, Activation/config refactors |

## Dependencies

- Gateway (#1512) must publish the v2 compatibility flag on health and `/rebalancing/execute`; SDK (#1511) has to consume the new metric keys before issue #1514 can close.
- Validate ko/en parity via `uv run mkdocs build`.
