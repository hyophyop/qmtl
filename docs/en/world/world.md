---
title: "QMTL Worlds — Strategy Lifecycle Specification"
tags: [world, strategy]
author: "QMTL Team"
last_modified: 2026-04-03
---

{{ nav_links() }}

# QMTL Worlds — Strategy Lifecycle Specification v1

This page is the top-level contract for World as the strategy lifecycle unit in QMTL. Detailed runtime, API, and operations material has been split into companion documents; this page stays focused on ownership, policy flow, and the way World controls Runner plus the order path.

> **Terminology:** `World` is the canonical term across QMTL. The older `Realm` proposal was not adopted.

- Baseline documents:
  - [QMTL Normative Architecture](../architecture/architecture.md)
  - [Gateway](../architecture/gateway.md)
  - [DAG Manager](../architecture/dag-manager.md)
  - [WorldService](../architecture/worldservice.md)
- Repository boundary:
  - reusable framework features belong under `qmtl/`
  - alpha strategies belong under repository-root `strategies/`
- Default data handler:
  - `SeamlessDataProvider` remains the default history/backfill path

## 0. Core Loop Summary

World organizes the Core Loop in four stages:

1. Strategy submission -> world binding (`Runner.submit(..., world=...)`, WSB)
2. World evaluation (`/worlds/{id}/evaluate`) -> decision envelopes
3. Activation/gating (`/worlds/{id}/activation`, event stream) -> order-path control
4. Capital allocation (`/allocations`, `/rebalancing/*`) -> world/strategy allocations

This document explains those stages at the contract level and delegates endpoint, runtime, and operator detail to linked companion docs.

## 1. Scope and Non-Goals

Objectives

- Treat World as the top-level abstraction that evaluates, selects, and governs strategies.
- Combine data currency, sample sufficiency, performance thresholds, correlation/risk constraints, and hysteresis into promotion/demotion decisions.
- Keep Runner on a single world-driven entry surface while reusing Gateway, DAG Manager, and existing metrics.

Non-goals

- No new distributed scheduler, message broker, or graph model.
- Strategy deployment/process management remains an external operational concern.

## 2. Concepts and Data

- **World**: execution boundary for a strategy set. Example: `crypto_mom_1h`
- **WorldPolicy(vN)**: versioned YAML snapshot
- **StrategyInstance**: per `(strategy, params, side, world)` instance
- **Activation Table**: lightweight cache of active strategies and weights
- **Audit Log**: evaluation inputs, Top-K outputs, and 2-Phase apply results

Recommended storage

- policy definitions: `config/worlds/<world_id>.yml`
- activation table: Redis `world:<world_id>:active`
- audit log and policy versions: Gateway/WorldService database extension

## 3. States and Transitions (Minimal)

- Runner does not choose execution mode; it follows world decisions.
- Operational world states are limited to `evaluating`, `applying`, and `steady`.
- 2-Phase apply summary:
  1. Freeze/Drain
  2. Switch
  3. Unfreeze
- Every step is tracked by an idempotent `run_id` and leaves a rollback point.

Node, queue, and tag-level state reuse the existing DAG Manager and SDK contracts.

## 4. Policy DSL (Concise)

World uses a minimal YAML shape: `Gates -> Score -> Constraints -> Top-K -> Hysteresis`.

```yaml
world: crypto_mom_1h
version: 1

data_currency:
  max_lag: 5m
  min_history: 60d
  bar_alignment: exchange_calendar

selection:
  gates:
    and:
      - sample_days >= 30
      - trades_60d >= 40
      - sharpe_mid >= 0.60
      - max_dd_120d <= 0.25
  score: "sharpe_mid + 0.1*winrate_long - 0.2*ulcer_mid"
  topk:
    total: 8
    by_side: { long: 5, short: 3 }
  constraints:
    correlation:
      max_pairwise: 0.8
    exposure:
      gross_budget: { long: 0.60, short: 0.40 }
      max_leverage: 3.0
      sector_cap: { per_sector: 0.30 }
  hysteresis:
    promote_after: 2
    demote_after: 2
    min_dwell: 3h

campaign:
  backtest:
    window: 180d
  paper:
    window: 30d
  common:
    min_sample_days: 30
    min_trades_total: 100

position_policy:
  on_promote: flat_then_enable
  on_demote: disable_then_flat
```

Policy engine detail remains in [Policy Engine](policy_engine.md).

## 5. Decision Flow (Summary)

The decision order is `data currency -> gates -> score -> constraints -> Top-K -> hysteresis`.

```python
def decide_initial_mode(now, data_end, max_lag):
    return "active" if (now - data_end) <= max_lag else "validate"

def gate_metrics(m, policy):
    if m.sample_days < policy.min_sample_days:
        return "insufficient"
    if m.trades_60d < policy.min_trades:
        return "insufficient"
    return "pass" if eval_expr(policy.gates, m) else "fail"

def apply_hysteresis(prev, checks, h):
    dwell_ok = time_in_state(prev) >= h.min_dwell
    if checks.consecutive_pass >= h.promote_after and dwell_ok:
        return "PROMOTE"
    if checks.consecutive_fail >= h.demote_after and dwell_ok:
        return "DEMOTE"
    return "HOLD"
```

## 6. Integration Points

- Runner: single world-driven execution surface
- Gateway: submission/state/queue lookup plus world API proxy
- DAG Manager: NodeID/topic/tag resolution SSOT
- Metrics: reuse SDK/Gateway/DAG Manager Prometheus exports

### 6.1 World-first runtime integration

Runner/CLI entrypoints, fallback rules, and activation interaction live in [World Runtime Integration](world_runtime_integration.md).

<a id="62-데이터-preset-onramp"></a>
### 6.2 Data preset on-ramp

The world is the SSOT for data presets, and Runner/CLI should wire Seamless from `world + preset` alone. See [World Data Preset Contract](world_data_preset.md) for the full schema and preset map.

### 6.3 Tag/interval to queue routing

TagQueryNode, Gateway `/queues/by_tag`, and DAG Manager topic namespaces must share one tag/interval contract. The detailed routing rules are documented in [World Data Preset Contract](world_data_preset.md).

## 7. Order Gate

- Form: shared SDK `OrderGateNode` or equivalent adapter
- Placement: immediately before brokerage/order nodes
- Default policy: block unless activation explicitly opens the path
- During 2-Phase apply, Freeze/Drain semantics take priority

Envelope detail and fail-closed rules live in [World Order Gate](world_order_gate.md).

## 8. Boundaries and Principles

- Reuse first: keep Gateway, DAG Manager, SDK Runner, and existing metrics wherever possible.
- Simplicity first: keep world logic centered on evaluation -> activation -> gate.
- Conservative defaults: hysteresis, cooldowns, and risk cuts should default on.
- Repository boundaries stay strict: shared features in `qmtl/`, alpha strategies in `strategies/`.

## 9. Companion Documents

- [World Runtime Integration](world_runtime_integration.md)
- [World Data Preset Contract](world_data_preset.md)
- [World Order Gate](world_order_gate.md)
- [World Rollout and Operations](world_rollout_and_ops.md)
- [World Registry](world_registry.md)
- [World API Reference](../reference/api_world.md)
- [World Event Stream Runtime](../architecture/world_eventstream_runtime.md)
- [Centralized Rebalancing Policy](rebalancing.md)
- [Policy Engine](policy_engine.md)

{{ nav_links() }}
