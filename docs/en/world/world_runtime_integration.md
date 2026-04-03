---
title: "World Runtime Integration"
tags: [world, runtime]
author: "QMTL Team"
last_modified: 2026-04-03
---

{{ nav_links() }}

# World Runtime Integration

This page explains how a world drives Runner/CLI execution modes and activation gates. The top-level contract remains [World Spec](world.md); SSOT boundaries remain with [WorldService](../architecture/worldservice.md) and [Gateway](../architecture/gateway.md).

## 1. Single entry surface

- CLI:
  - `qmtl tools sdk run --world-id <id> --gateway-url <url>`
  - `qmtl tools sdk offline`
- SDK:
  - `Runner.submit(strategy_cls, world=...)`
  - `Runner.offline(...)`

The core rule is that Runner does not choose execution mode locally. World decisions and activation envelopes drive the runtime path.

## 2. Execution flow

1. Runner receives `world_id` and calls Gateway `GET /worlds/{id}/decide`.
2. Gateway relays the WorldService decision and may add a safely downgraded `compute_context`.
3. Runner treats that result as read-only control input and adjusts validation/order gating accordingly.
4. Activation state is refreshed via `GET /worlds/{id}/activation` or the event-stream bootstrap path.

## 3. Fallback rules

- If Gateway is unavailable or the decision TTL expires, the runtime falls back to fail-closed defaults.
- If activation is unknown or stale, the order path stays closed.
- `--world-file` can reproduce the same policy inputs locally, but it does not replace an authoritative live activation decision.
- No fallback path may upgrade beyond the authoritative `effective_mode` produced by the world.

## 4. Interaction with the order gate

- Mode decisions and activation are different envelopes, but runtime must interpret them together.
- Even when `effective_mode` is `paper` or `live`, orders stay blocked if activation is closed.
- During 2-Phase apply, Freeze/Drain semantics take precedence over everything else.

See [World Order Gate](world_order_gate.md) for the order-path contract and [World Event Stream Runtime](../architecture/world_eventstream_runtime.md) for the streaming side.

## 5. Immediate-live worlds

Immediate-live worlds need an explicit permission rail.

- `allow_live` or equivalent world-scoped authorization must be present.
- Relaxed observation or sample gates do not remove safe downgrade behavior.
- Operators must be able to audit live paths through world-scoped RBAC and audit logs.

{{ nav_links() }}
