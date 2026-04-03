---
title: "World Lifecycle Contract"
tags:
  - contracts
  - core-loop
  - world
author: "QMTL Team"
last_modified: 2026-04-03
---

{{ nav_links() }}

# World Lifecycle Contract

## Related documents

- [Product Contracts Overview](README.md)
- [Core Loop Contract](core_loop.md)
- [Core Loop × WorldService — Campaign Automation and Promotion Governance](../architecture/core_loop_world_automation.md)
- [WorldService](../architecture/worldservice.md)
- [World Activation Runbook](../operations/activation.md)
- [World Validation Governance](../operations/world_validation_governance.md)

## Summary

Concept ID: `CONTRACT-WORLD-LIFECYCLE`

The world lifecycle contract explains, from the product surface, how a strategy is observed and promoted inside a world.

Core rules:

- Stage transitions are determined by world policy and WorldService.
- Callers submit only the strategy and the world; they do not directly choose backtest → paper → live stages.
- `campaign/tick` is a recommendation surface, not an implicit apply operation.
- Live promotion and capital application remain auditable operational steps.

## Stage model

At the product level, the lifecycle contains these stages:

- `backtest`
- `paper` or `dryrun`
- `live`

Two facts matter most to users:

- Stages are not chosen by a client-side mode; they follow world-policy outcomes.
- When the system is unsure or stale, it downgrades toward the safer path instead of promoting further.

## Evaluation Run contract

Worlds track evaluation, validation, and promotion candidacy through Evaluation Runs.

From the user’s perspective, this means:

- the same strategy has stage-aware evaluation history
- metrics can continue to update during paper/live observation windows
- clients do not need to assemble every metric manually

The normative sourcing order and enrichment rules live in [Core Loop × WorldService — Campaign Automation and Promotion Governance](../architecture/core_loop_world_automation.md).

## Campaign Tick contract

`POST /worlds/{id}/campaign/tick` is, at the product level, a “recommended next action” surface.

It promises:

- the system reads current phase and observation state
- it returns action hints such as `idempotency_key`, `suggested_run_id`, and `suggested_body`
- it does not trigger side effects by itself

In other words, `tick` is a **decision recommendation** surface, not an **execution** surface.

## Live promotion governance

At the product-contract level, live promotion is not pure automation. It is the combination of **policy + operational governance**.

Minimum contract:

- if `allow_live=false`, live promotion does not open
- if observation windows, required metrics, or risk-snapshot requirements are not satisfied, promotion remains blocked
- modes such as `manual_approval` and `auto_apply` do not mean that observation or validation is skipped

## Read-only vs. operational surfaces

Read-only surfaces:

- decision/activation/allocation snapshots in submit results
- campaign status
- campaign tick recommendations

Operational surfaces:

- activation apply / override
- live promotion approval
- allocation / rebalancing apply
- rollback / freeze / drain

The product contract defines the read-only surfaces and baseline automation. Operational surfaces remain separately governed and auditable.

## Next documents

- For backend automation contracts and metric-sourcing rules, see [Core Loop × WorldService — Campaign Automation and Promotion Governance](../architecture/core_loop_world_automation.md).
- For operator approval and rollback, see [World Activation Runbook](../operations/activation.md).
- For override review governance, see [World Validation Governance](../operations/world_validation_governance.md).

{{ nav_links() }}
