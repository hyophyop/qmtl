---
title: "Centralized Rebalancing Policy"
tags: [world, rebalancing]
author: "QMTL Team"
last_modified: 2025-11-04
---

# Centralized Rebalancing Policy

This document specifies a pluggable, centralized rebalancer that adjusts positions when world/strategy allocations change, while keeping strategy nodes pure (intent-only) and minimizing fees via venue/symbol netting.

## Goals

- Automatically scale exposures when `world_alloc` or per-strategy `strategy_alloc` changes.
- Centralized netting across strategies, per (venue, symbol), to reduce churn and fees.
- Execution relies on position snapshots only (no order-state dependency).
- Start with a simple rule-based implementation; allow drop-in replacements later.

## Data Contracts

- Input snapshots: `PortfolioSnapshot` (see reference/api/portfolio.md; reference/schemas/portfolio_snapshot.schema.json)
  - `positions[symbol] = { qty, avg_cost, mark }`
  - Provide per-strategy snapshots for `(world_id, strategy_id)` scope
- Rebalance context:
  - `total_equity`: total assets across worlds
  - `world_alloc_before/after`: world allocation ratios (0.0–1.0)
  - `strategy_alloc_before/after`: per-strategy allocation ratios (0.0–1.0)
  - `positions`: flattened rows with optional `venue` (exchange)
  - `min_trade_notional`, `lot_size_by_symbol`: dust suppression/rounding

## Rule: Proportional Rebalancing

- World scale: `gw = world_after / world_before`
- Strategy scale: `gs[s] = strategy_after[s] / strategy_before[s]` (fallback to `gw`)
- Effective scale per position of strategy `s`:
  - downscale: `g = min(gw, gs[s])`
  - upscale: `g = max(gw, gs[s])`
- Apply `g` to each position's notional (`qty * mark`) to get the target notional, compute deltas, then aggregate by (venue, symbol)
- Drop changes below `min_trade_notional`; round to `lot_size` if provided

Example:
- If world `a` changes 0.3 → 0.2, then `gw = 2/3`
- Strategy `b` in world `a` keeps the same fraction of the world ⇒ `gs[b] = 2/3`
- Positions are reduced to 2/3 of their current notional via aggregated deltas; execution reconciles to targets using position-based policies

## Interface and Default Implementation

- Interface: `qmtl/services/worldservice/rebalancing/base.py`
  - `Rebalancer.plan(RebalanceContext) -> RebalancePlan`
  - Output includes aggregated `delta_qty` per (venue, symbol) and scaling meta
- Default: `ProportionalRebalancer`
  - Implements the proportional rule with netting, dust suppression, and rounding
  - Combination rule: when per-strategy allocations are provided on a total-equity basis, apply `g_s = after_total / before_total` directly (scale the strategy vector). If missing, cascade the world scale `g_w = world_after / world_before`.

## Multi-World Planning

- Rebalancing multiple worlds in one pass allows netting offsetting exposures across worlds (same venue/symbol), reducing fee churn.
- Context/plan types:
  - Input: `MultiWorldRebalanceContext`
    - `world_alloc_before/after`: per-world fractions (of total equity)
    - `strategy_alloc_*_total`: optional (omit to use world-scale cascade)
    - `positions`: all worlds’ positions (each row carries `world_id`)
  - Output: `MultiWorldRebalancePlan`
    - `per_world`: per-world `RebalancePlan`
    - `global_deltas`: net view across worlds (analysis/shared-account netting)
- Implementation: `MultiWorldProportionalRebalancer`
  - Applies `ProportionalRebalancer` per world and computes a global net delta view.
  - Execute orders per world by default; only apply global netting in shared-account mode.

## Strategy Weight Triggers and Cascade

- No manual tuning here. Strategy weights change only via two triggers:
  1) Intra-world performance weighting module updates (e.g., PnL/metrics)
  2) Cascade from a world allocation change (preserve intra-world proportions; apply world scale)
- Using the rebalancer:
  - If the performance module updated weights: pass `strategy_alloc_after_total` to reflect them
  - Otherwise omit and the world scale cascades to strategies, preserving relative shares

## Execution Coupling

- Feed `delta_qty` to execution which converges using position snapshots:
  - Reductions via `reduce-only` (if supported)
  - Open remaining deltas; for flips use "flatten-then-open" or safe "direct-flip"

## Pluggability

- Replace with cost-aware, slippage-aware, or risk-constrained models without changing callers. New modules consume `RebalanceContext` and return `RebalancePlan`.

## Caveats

- Respect venue/symbol lot sizes and minimums to avoid overshoot/undershoot.
- In order-unreliable environments, execution must treat position snapshots as the source of truth.
- Normalize symbol codes across venues in the venue/symbol resolver step.

{{ nav_links() }}
