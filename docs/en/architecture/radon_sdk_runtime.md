---
title: "SDK Runtime Radon Plan"
tags: ["radon", "sdk", "runtime"]
author: "QMTL Team"
last_modified: 2025-11-13
---

{{ nav_links() }}

# SDK Runtime Radon Plan

The runtime/SDK tier ferries Gateway/DAG contracts to execution nodes and WorldService APIs. The 2025‑11 scan reported 30+ C/D/E hotspots inside `qmtl/runtime` and `qmtl/runtime/sdk`, primarily SeamlessDataProvider, history warmup, and `alpha_performance` transforms. This plan lowers that complexity while unifying the `alpha_performance` metric contract across SDK ↔ Gateway ↔ WorldService.

## Findings

| Area | Path | Radon | Notes |
| --- | --- | --- | --- |
| Execution Context | `resolve_execution_context` {{ code_url('qmtl/runtime/sdk/execution_context.py#L93') }} | E (31) | Backtest/Live/Shadow branches handled in one function |
| Seamless Provider | `SeamlessDataProvider.ensure_data_available` {{ code_url('qmtl/runtime/sdk/seamless_data_provider.py#L1486') }} | E (31) | Domain gating, artifact download, downgrade logic fused together |
| Seamless Provider | `_domain_gate` {{ code_url('qmtl/runtime/sdk/seamless_data_provider.py#L1176') }}, `_fetch_seamless` {{ code_url('qmtl/runtime/sdk/seamless_data_provider.py#L1630') }}, `_subtract_ranges` {{ code_url('qmtl/runtime/sdk/seamless_data_provider.py#L2692') }} | D (22‑24) | Mix of config, network I/O, and arithmetic |
| History Warmup | `HistoryWarmupService.warmup_strategy` {{ code_url('qmtl/runtime/sdk/history_warmup_service.py#L356') }} | D (22) | Request orchestration, replay, and validation live in one loop |
| Activation Feed | `ActivationManager._on_message` {{ code_url('qmtl/runtime/sdk/activation_manager.py#L111') }} | D (24) | WS message parsing, validation, cache updates joined together |
| Alpha Metrics | `alpha_performance_node` {{ code_url('qmtl/runtime/transforms/alpha_performance.py#L49') }} | D (21) | Metric math, execution-cost adjustments, and formatting tightly coupled |
| Dispatch | `TradeOrderDispatcher.dispatch` {{ code_url('qmtl/runtime/sdk/trade_dispatcher.py#L72') }} | C (20) | Routing, retry, and telemetry share the same block |

## Goals

- Reduce every highlighted D/E block to **B or better**; target A for `alpha_performance`
- Document the `alpha_performance` metric keys/units across SDK, Gateway, and WorldService, with parser defaults that ignore unknown keys
- Introduce **testable builders** for SeamlessDataProvider/history warmup so side effects stay isolated
- Enforce Radon in CI via `uv run --with radon -m radon cc -s -n C qmtl/runtime qmtl/runtime/sdk`

## Refactor tracks

### 1. Execution context & dispatch normalization

- Replace the monolithic `resolve_execution_context` with strategy objects per mode (backtest/live/shadow/replay) and propagate Gateway health capability bits (`compute_context`, `rebalance_schema_version`, `alpha_performance`) unchanged.
- Reshape `TradeOrderDispatcher.dispatch` into three stages (routing → retry → metrics) using a `DispatchEnvelope` dataclass to keep CC < 10 and allowing deterministic tests.

### 2. SeamlessDataProvider modularization

- Split `ensure_data_available` into four steps: domain gating (`_domain_gate`), artifact selection/download, range arithmetic, downgrade handling. Each step becomes its own helper so unit tests can stub boundaries.
- Keep `_fetch_seamless` and `_subtract_ranges` pure, inject I/O via callbacks, and move publication side effects into a dedicated event bus helper.

### 3. History warmup pipeline

- Rebuild `HistoryWarmupService.warmup_strategy` as a flow graph (decide request → ensure history → gap analysis → replay → validation). Each node is a generator/async helper, making reuse with `ensure_strict_history` trivial.
- Relocate `_ensure_node_with_plan` and `replay_events_simple` into testable modules under `qmtl/runtime/sdk/tests`.

### 4. Activation/WS safeguards

- Feed Pydantic models into `ActivationManager._on_message`, adopt the “ignore missing, gate new via feature flag” policy required by issue #1514.
- Extract `weight_for_side` into a pure helper so additional metrics (e.g., `alpha_performance`) can be recorded safely.

### 5. Alpha performance restructuring

- Decompose `alpha_performance_node` into calculator classes plus dedicated execution-cost adjusters to drive CC < 10.
- Emit results under the `alpha_performance.{metric}` namespace and keep keys/units identical to the WorldService spec from (#1513).
- Update the SDK parser to ignore missing keys and gate new ones through flags, satisfying issue #1514’s parser checklist item.

### 6. Docs & tests

- Cross-link this plan from `docs/en/guides/sdk_tutorial.md` and `docs/en/reference/report_cli.md` wherever the metric contract is mentioned.
- Test recipe: `uv run -m pytest -W error -n auto qmtl/runtime/tests qmtl/runtime/sdk/tests` plus the timeout preflight (`PYTHONFAULTHANDLER=1 uv run --with pytest-timeout -m pytest -q --timeout=60 --timeout-method=thread --maxfail=1`).
- Radon gate: `uv run --with radon -m radon cc -s -n C qmtl/runtime qmtl/runtime/sdk`.

## Timeline

| Phase | Duration | Deliverables |
| --- | --- | --- |
| Phase 1 | 3 days | ExecutionContext/Dispatcher modules, `alpha_performance` calculator draft, parser fallback |
| Phase 2 | 4 days | Modular SeamlessDataProvider, history warmup pipeline, unit tests |
| Phase 3 | 2 days | Activation parser updates, docs/Radon snapshots, `uv run mkdocs build` |

## Dependencies

- Consume the compatibility flag/health bits emitted by the Gateway/DAG plan (#1512) as soon as they go live.
- Mirror the `MultiWorldRebalanceRequest` v2 + `alpha_performance` contract finalized by WorldService (#1513).
- Issue #1514’s “SDK parser update” item is satisfied only when Phase 3 completes.
