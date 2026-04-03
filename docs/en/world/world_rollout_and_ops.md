---
title: "World Rollout and Operations"
tags: [world, rollout, operations]
author: "QMTL Team"
last_modified: 2026-04-03
---

{{ nav_links() }}

# World Rollout and Operations

This page records the safety rails, phased rollout, and multi-world resource rules used when bringing world features into production. The normative interface remains [World Spec](world.md); operational procedures remain in the [operations guides](../operations/README.md).

## 1. Required safety rails

- Data currency gate: keep compute-only until `now - data_end <= max_lag`.
- Sample sufficiency: treat outputs as advisory until minimum periods and trade counts are met.
- Two-phase transition: track `Freeze/Drain -> Switch -> Unfreeze` with idempotent `run_id`.
- Apply requests must use `run_id` plus `etag` and remain traceable in the audit log.
- World-level drawdown, VaR, or leverage violations close the gate immediately.

## 2. Recommended SLOs and alerts

Key metrics:

- `world_eval_duration_ms_p95`
- `world_apply_duration_ms_p95`
- `world_activation_skew_seconds`
- `promotion_fail_total`
- `demotion_fail_total`
- `world_apply_failure_total`
- `world_apply_run_total`
- `world_allocation_snapshot_stale_ratio`
- `controlbus_apply_ack_latency_ms{phase}`

Suggested alerts:

- `increase(world_apply_failure_total[5m]) > 0`
- `world_allocation_snapshot_stale_ratio > 0.1`
- `world_activation_skew_seconds > 5`

## 3. Multi-world resource isolation

- Start with World-SILO isolation.
- If shared nodes are introduced for cost reasons, fix NodeID hashing and namespace boundaries first.
- Shared-node Mark-and-Sweep should always run with Drain semantics.

## 4. Phased rollout

### Phase 0

- Prepare world policy docs and sample YAML files.
- Normalize metric-producing nodes or existing metric exports.

### Phase 1

- Add the read-only evaluator and activation table.
- Expose `GET /worlds/{id}/activation` and `POST /worlds/{id}/evaluate`.

### Phase 2

- Add `POST /worlds/{id}/apply`.
- Add risk-cut/circuit-breaker paths.
- Add promotion/demotion/failure/latency metrics.

### Phase 3

- Introduce the SDK order gate.
- Update examples and operator docs.

### Phase 4

- Add multi-world optimization and shared-node namespaces.

## 5. Runner/CLI transition

- `qmtl tools sdk run --world-id ...`
- `qmtl tools sdk offline`
- Keep docs and samples centered on the world-first surface.

Operational flows and approvals live in:

- [World Activation Runbook](../operations/activation.md)
- [World Validation Governance](../operations/world_validation_governance.md)
- [ControlBus Operations](../operations/controlbus_operations.md)
- [Rebalancing Execution](../operations/rebalancing_execution.md)

{{ nav_links() }}
