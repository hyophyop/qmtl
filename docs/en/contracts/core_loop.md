---
title: "Core Loop Contract"
tags:
  - contracts
  - core-loop
  - product
author: "QMTL Team"
last_modified: 2026-04-03
---

{{ nav_links() }}

# Core Loop Contract

## Related documents

- [Product Contracts Overview](README.md)
- [World Lifecycle Contract](world_lifecycle.md)
- [Architecture Overview](../architecture/architecture.md)
- [Gateway](../architecture/gateway.md)
- [WorldService](../architecture/worldservice.md)

## Summary

Concept ID: `CONTRACT-CORE-LOOP-GOLDEN-PATH`

From the strategy author’s perspective, the QMTL Core Loop is:

> write strategy -> `Runner.submit(..., world=...)` -> inspect result -> refine strategy

This contract guarantees the following expectations.

- There is one submission entrypoint: `Runner.submit(..., world=...)`.
- Data on-ramp, replay/backtest, evaluation requests, and WorldService result surfacing are handled by the system.
- WorldService provides the authoritative decision surface.
- Live promotion, allocation application, approvals, and audit remain explicit operational steps.

## Contract scope

This page defines the **product-facing contract** only.

- Includes:
  - the single submission entrypoint
  - the meaning of the result returned to the user
  - the handoff boundary between read-only observation and operations
- Excludes:
  - low-level service call sequences
  - approval and rollback procedures
  - detailed implementation-status reporting

## Golden path

### 1. Strategy code expresses strategy logic only

- Strategy authors define signal logic and required data.
- Data supply, backfill, replay, and world-policy evaluation are owned by system layers.

### 2. Submission converges to one entrypoint

- The submission surface converges on `Runner.submit(..., world=...)`.
- Client-side `mode` is not part of the product contract.
- `world` supplies the domain context, while stage selection (backtest/paper/live) is managed by world policy and WorldService.

### 3. Results separate “precheck + authoritative world result”

- Local precheck is advisory.
- Authoritative status, weights, activation, and world-level outcome come from WorldService.
- If the system cannot establish a safe world decision, it downgrades into safe mode.

### 4. Users stay focused on the improve loop

- After submission, users inspect world performance, contribution, and reasons.
- Operational application steps are handed off to explicit operator workflows.

## Input contract

### Required inputs

- strategy
- `world`

### Optional expert inputs

- `preset`
- `data_preset`
- `returns`
- `auto_returns`

These are expert overrides, not required knowledge for the default path.

## Result contract

The submission result must surface at least:

- local precheck output
- WorldService evaluation output
- decision/activation world state
- read-only supporting context such as allocation snapshots
- safe mode / downgraded indicators

Core rules:

- Precheck is advisory; WorldService remains authoritative.
- Allocation information is observational; it does not mean capital was automatically applied.
- A single submit call does not guarantee live entry.

## Automation boundary

The Core Loop contract does not promise that every operational action is automatic.

Handled automatically:

- strategy submission
- default data on-ramp
- replay/backtest
- policy-evaluation request
- result surfacing

Left as explicit operations:

- live promotion approval
- allocation/rebalancing application
- rollback, audit, emergency circuit-breaking

## Next documents

- For stage transitions and promotion governance, see [World Lifecycle Contract](world_lifecycle.md).
- For SSOT boundaries and internal service responsibilities, see [Architecture Overview](../architecture/architecture.md) and [WorldService](../architecture/worldservice.md).
- For operations, see [World Activation Runbook](../operations/activation.md) and [Rebalancing Execution Adapter](../operations/rebalancing_execution.md).

{{ nav_links() }}
