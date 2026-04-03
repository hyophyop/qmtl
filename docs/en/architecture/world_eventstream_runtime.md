---
title: "World Event Stream Runtime"
tags: [architecture, world, controlbus, runtime]
author: "QMTL Team"
last_modified: 2026-04-03
---

{{ nav_links() }}

# World Event Stream Runtime

This page defines the runtime boundary through which world activation, queue, and policy events reach SDK clients via Gateway without exposing the internal ControlBus implementation. SSOT remains with [WorldService](worldservice.md) and [DAG Manager](dag-manager.md); the internal fan-out fabric remains [ControlBus](controlbus.md).

## 1. Role split

- **WorldService**: world/policy/activation SSOT
- **DAG Manager**: graph/node/queue SSOT
- **ControlBus**: internal distribution/fan-out bus; not exposed directly
- **Gateway**: external ingress plus event-stream descriptor issuance and fan-out
- **SDK/Runner**: consumer of an opaque stream contract

## 2. EventStreamDescriptor

Gateway returns an opaque descriptor from `POST /events/subscribe`.

- `stream_url`: WebSocket URL on the Gateway domain
- `token`: JWT scoped to world/topic/strategy
- `topics`: normalized topic list
- `expires_at`: re-subscribe deadline
- `fallback_url`: backup path when the primary stream fails

Clients do not need to know the internal ControlBus topology or topic naming.

## 3. Event types

- `ActivationUpdated`
  - `world_id`, `strategy_id`, `side`, `active`, `weight`, `effective_mode`, `etag`, `run_id`, `ts`
- `QueueUpdated`
  - `tags[]`, `interval`, `queues[]`, `etag`, `ts`
- `PolicyUpdated`
  - `world_id`, `version`, `checksum`, `status`, `ts`

## 4. Ordering, idempotency, and recovery

- Ordering is guaranteed only per key (`world_id`, `(tags, interval)`).
- Duplicates are allowed; consumers must de-duplicate by `etag` or `run_id`.
- On stream failure:
  1. use `fallback_url` or HTTP polling
  2. reconcile via `GET /worlds/{id}/activation` or `GET /queues/by_tag`
  3. re-issue `POST /events/subscribe` if the token expires

ACK and sequence-gap recovery policy is documented in [ACK/Gap Resync RFC (Draft)](../design/ack_resync_rfc.md).

## 5. Interface map

- SDK → Gateway
  - `/strategies`, `/queues/by_tag`, `/worlds/*`, `/events/subscribe`
- Gateway → WorldService
  - `/worlds/*`, `/activation`, `/decide`, `/evaluate`, `/apply`
- Gateway → DAG Manager
  - `get_queues_by_tag`, diff and queue queries
- WorldService / DAG Manager → ControlBus
  - publish activation, policy, and queue events
- Gateway → ControlBus
  - subscribe then relay to SDK clients

## 6. Latency budgets

- SDK → Gateway submit p95 ≤ 150ms
- queue lookup p95 ≤ 200ms
- event fan-out lag p95 ≤ 200ms
- activation skew ≤ 2s

The default failure posture is always fail-closed: if the world decision is unavailable, stay compute-only; if activation cannot be confirmed, keep the order gate closed.

## 7. Relationship diagram

```mermaid
graph LR
  subgraph Client
    SDK[SDK / Runner]
  end
  subgraph Edge
    GW[Gateway]
  end
  subgraph Core
    WS[WorldService (SSOT Worlds)]
    DM[DAG Manager (SSOT Graph)]
    CB[(ControlBus - internal)]
  end

  SDK -- HTTP submit/decide/activation --> GW
  GW -- proxy --> WS
  GW -- proxy --> DM
  WS -- publish --> CB
  DM -- publish --> CB
  GW -- subscribe --> CB
  GW -- opaque stream --> SDK
```

{{ nav_links() }}
