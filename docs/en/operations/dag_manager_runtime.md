---
title: "DAG Manager Runtime and Deployment Profiles"
tags: [operations, dagmanager, runtime]
author: "QMTL Team"
last_modified: 2026-04-03
---

{{ nav_links() }}

# DAG Manager Runtime and Deployment Profiles

## Related Documents

- [DAG Manager](../architecture/dag-manager.md)
- [Backend Quickstart](backend_quickstart.md)
- [Config CLI](config-cli.md)
- [DAG Manager Compute Context Rollout](dagmanager_diff_context_rollout.md)
- [Canary Rollout](canary_rollout.md)

## Purpose

This document captures DAG Manager runtime requirements, Neo4j/Kafka/ControlBus dependencies, preflight checks, and incident-response points from an operator perspective.

- The normative meaning of graph SSOT, DAG diff, and queue orchestration belongs in [DAG Manager](../architecture/dag-manager.md).
- This page focuses on which infrastructure is required and what operators should check first when the service degrades.

## Runtime Profiles

### `profile: dev`

- Allow an in-memory graph repository when `dagmanager.neo4j_dsn` is empty.
- Allow in-memory queue/topic behavior when `dagmanager.kafka_dsn` is empty.
- Disable queue-update publishing when `dagmanager.controlbus_dsn` or `dagmanager.controlbus_queue_topic` are empty.

### `profile: prod`

- The following are fail-fast requirements.
  - `dagmanager.neo4j_dsn`
  - `dagmanager.kafka_dsn`
  - `dagmanager.controlbus_dsn`
  - `dagmanager.controlbus_queue_topic`
- Do not allow in-memory fallbacks to count as valid production operation.
- `qmtl config validate` should block these as errors, not warnings.

## Preflight Checks

1. `uv run qmtl config validate --config <path> --offline`
2. Confirm Neo4j DSN and credentials
3. Confirm Kafka/Redpanda bootstrap and topic policy
4. Confirm the ControlBus queue topic exists
5. Apply constraints/indexes with `qmtl --admin dagmanager-server neo4j-init ...` when needed

## External Dependencies

- **Neo4j**: SSOT for the global strategy graph
- **Kafka/Redpanda**: data-queue and commit-log boundary
- **ControlBus**: control-event fan-out such as `QueueUpdated`
- **Gateway**: submission ingress and diff caller

## Incident Checklist

- Neo4j unreachable:
  - in prod, startup failure is expected
  - check constraints/indexes and leader health first
- Kafka/Redpanda outage:
  - topic orchestration and queue lifecycle stop, so inspect queue-update warnings first
  - if a canary or queue-namespace transition is in flight, read this together with [Canary Rollout](canary_rollout.md)
- ControlBus disabled:
  - confirm whether the service booted without queue-update fan-out
  - inspect broker/topic configuration together with [ControlBus/Queue Standards](controlbus_queue_standards.md)
- Unexpected in-memory fallback:
  - confirm dev settings did not leak into a production-like deployment

## Observability

- Health/status and diff-related metrics are documented in [Monitoring and Alerting](monitoring.md).
- Compute-context rollout issues should be read together with [DAG Manager Compute Context Rollout](dagmanager_diff_context_rollout.md).
- Graph snapshot/freeze procedures live in [DAG Snapshot and Freeze](dag_snapshot.md).

{{ nav_links() }}
