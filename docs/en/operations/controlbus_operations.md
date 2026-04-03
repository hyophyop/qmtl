---
title: "ControlBus Runtime and Incident Handling"
tags: [operations, controlbus, queue]
author: "QMTL Team"
last_modified: 2026-04-03
---

{{ nav_links() }}

# ControlBus Runtime and Incident Handling

## Related Documents

- [ControlBus](../architecture/controlbus.md)
- [ControlBus/Queue Standards](controlbus_queue_standards.md)
- [World Activation Runbook](activation.md)
- [ACK/Gap Resync RFC (Draft)](../design/ack_resync_rfc.md)

## Purpose

This document captures broker/topic requirements, dev/prod operating differences, and incident-response points around lag, gaps, and ACK handling.

- Event semantics and envelope schemas belong in [ControlBus](../architecture/controlbus.md).
- This page focuses on what operators should check first when brokers are missing, lag grows, or ACK sequencing degrades.

## Runtime Profiles

### `profile: dev`

- ControlBus may be disabled for local execution.
- In that mode, publishers and consumers emit warnings and skip I/O.
- Activation/policy/queue updates may exist locally without downstream fan-out.

### `profile: prod`

- ControlBus is mandatory.
- If brokers/topics are missing or Kafka clients cannot start, Gateway, WorldService, and DAG Manager should fail fast.
- Topic namespaces, retention, and consumer-group rules follow [ControlBus/Queue Standards](controlbus_queue_standards.md).

## Operational Checklist

- Topic presence
  - `activation`
  - `control.activation.ack`
  - `queue`
  - `policy`
  - `sentinel_weight`
- Consumer-group health
  - Gateway relay consumer
  - WorldService control/risk-hub consumers
  - retry and DLQ policies where applicable
- ACK/gap timeout
  - `activation_gap_timeout_ms`
  - stale-relay alert thresholds

## Incident Checklist

- Broker outage:
  - in prod, treat this as an incident, not degraded normal operation
  - first confirm fail-fast behavior and restart loops across Gateway, WorldService, and DAG Manager
- Lag growth:
  - inspect consumer-group lag, dropped-subscriber counts, and event-fanout metrics together
  - if world activation appears stale, read this together with [World Activation Runbook](activation.md)
- ACK gap or out-of-order delivery:
  - inspect buffering, forced resequencing, and dropped-gap events for `requires_ack=true` flows
  - interpret the operating standard together with [ACK/Gap Resync RFC (Draft)](../design/ack_resync_rfc.md)
- Duplicate/replay behavior:
  - confirm dedupe by `etag`, `run_id`, and `idempotency_key`

## Observability

- Metrics and rehearsal scenarios are defined in [ControlBus/Queue Standards](controlbus_queue_standards.md).
- Activation apply should be read together with [World Activation Runbook](activation.md).
- Global monitoring and alert routing are managed in [Monitoring and Alerting](monitoring.md).

{{ nav_links() }}
