---
title: "World Order Gate"
tags: [world, order-gate, activation]
author: "QMTL Team"
last_modified: 2026-04-03
---

{{ nav_links() }}

# World Order Gate

This page defines the lightweight `OrderGate` contract that reflects world activation state into the order path. Activation remains owned by [WorldService](../architecture/worldservice.md), and stream fan-out remains described by [World Event Stream Runtime](../architecture/world_eventstream_runtime.md).

## 1. Purpose

- Insert a minimal order-enable/order-block rail without rewriting strategy logic.
- Enforce Freeze/Drain → Switch → Unfreeze safely during 2-Phase apply.
- Default to fail-closed when activation is unknown, stale, or unauthorized.

## 2. Shape and placement

- Form: shared SDK processing node or equivalent adapter (`OrderGateNode`).
- Placement: final gate immediately before brokerage/order nodes.
- Default policy: if activation is not explicitly open, block or reduce to zero size.

## 3. Input contract

- HTTP:
  - `GET /worlds/{world_id}/activation?strategy_id=...&side=...`
- Stream:
  - activation bootstrap frame
  - activation updates relayed from the ControlBus path

Minimal envelope:

```json
{
  "world_id": "crypto_mom_1h",
  "strategy_id": "abcd",
  "side": "long",
  "active": true,
  "weight": 1.0,
  "freeze": false,
  "drain": false,
  "effective_mode": "paper",
  "etag": "act:crypto_mom_1h:abcd:long:42",
  "run_id": "7a1b4c..."
}
```

## 4. Runtime rules

1. `active=false` blocks orders.
2. `freeze=true` or `drain=true` keeps the gate closed until a later phase opens it.
3. Stale activation or unavailable decisions downgrade to `active=false`, `weight=0.0`, and `effective_mode=compute-only`.
4. `weight` may scale size, but it must not be treated as a signal that bypasses the gate.

## 5. Relation to 2-Phase apply

- Freeze/Drain: close the order path and optionally permit reduce-only or flattening actions.
- Switch: replace the active set and weights.
- Unfreeze: reopen only after sequence and ACK rules are satisfied.

ACK and sequence recovery policy lives in [ACK/Gap Resync RFC (Draft)](../design/ack_resync_rfc.md) and [ControlBus Operations](../operations/controlbus_operations.md).

## 6. Observability

- `world_activation_skew_seconds`
- `controlbus_apply_ack_latency_ms{phase}`
- `world_apply_failure_total`
- activation update counters and stale-response counters

Operational handling belongs in [World Activation Runbook](../operations/activation.md) and [Determinism Runbook](../operations/determinism.md).

{{ nav_links() }}
