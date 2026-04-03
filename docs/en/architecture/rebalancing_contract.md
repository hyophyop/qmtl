---
title: "World Allocation and Rebalancing Contract"
tags:
  - architecture
  - worldservice
  - rebalancing
author: "QMTL Team"
last_modified: 2026-04-03
---

{{ nav_links() }}

# World Allocation and Rebalancing Contract

## Related documents

- [WorldService](worldservice.md)
- [Core Loop Contract](../contracts/core_loop.md)
- [World Lifecycle Contract](../contracts/world_lifecycle.md)
- [Rebalancing Execution Adapter](../operations/rebalancing_execution.md)
- [Rebalancing Schema Coordination](../operations/rebalancing_schema_coordination.md)

## Purpose

This document separates the WorldService allocation and rebalancing surfaces into an independent **normative contract**.

The primary role of the WorldService page is to describe world policy, decisions, and activation as SSOTs. Allocation and rebalancing are clearer when treated as their own control-plane contract.

## Summary

Concept ID: `CTRL-WORLD-ALLOCATION-TWO-STEP`

QMTL treats world allocation and rebalancing as a **standard two-step loop**:

1. evaluation/activation: observe world state through `Runner.submit(..., world=...)`
2. planning/application: manage capital allocation and execution plans through `/allocations`, `/rebalancing/plan`, and `/rebalancing/apply`

Core rules:

- allocation snapshots are a read-only observation contract
- real capital application and order submission remain auditable operational steps
- idempotency is maintained through `run_id` and `etag`

## Non-goals

- describing the full exchange-order transformation and submission flow
- documenting approval, rollback, or batch-submission runbooks
- re-explaining the product-facing submit contract

## Surface summary

### `POST /allocations`

- upserts world allocation and strategy-sleeve snapshots
- provides idempotency via `run_id` and a request-hash-based `etag`
- records the latest allocation snapshot and related execution outcome on success
- allows `execute=true` only when a compatible executor is configured

### `POST /rebalancing/plan`

- is a pure planning surface with no state persistence
- is used for operator review, simulation, and external execution pipelines

### `POST /rebalancing/apply`

- fixes an approved plan into an auditable and observable form
- does not directly mutate world allocation as its primary contract; it records and publishes an approved plan

## Idempotency and audit

- `run_id` is the standard key for retry and duplicate detection
- `etag` acts as optimistic concurrency control for payload mismatches under the same `run_id`
- apply remains an explicit auditable operations boundary

## Schema version and alpha metrics handshake

Concept ID: `CTRL-REBALANCING-SCHEMA-HANDSHAKE`

- `/rebalancing/plan` and `/rebalancing/apply` participate in `schema_version` negotiation
- when v2 is enabled, an `alpha_metrics` envelope is returned with the plan
- required-metrics mode may reject lower schema versions early
- ControlBus events must follow the same negotiated schema version

Operational rollout details live in [Rebalancing Schema Coordination](../operations/rebalancing_schema_coordination.md).

## Read-only vs. operational surfaces

Read-only surfaces:

- allocation snapshots surfaced through submit results
- `GET /allocations?world_id=...`
- `/rebalancing/plan`

Operational surfaces:

- `/allocations` upsert
- `/rebalancing/apply`
- external executor or order-submission paths

## Related operational documents

- Order translation and submission are covered in [Rebalancing Execution Adapter](../operations/rebalancing_execution.md).
- Activation, freeze, and drain procedures are covered in [World Activation Runbook](../operations/activation.md).

{{ nav_links() }}
