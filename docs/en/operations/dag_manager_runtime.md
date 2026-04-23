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

## GC Policy and Execution Boundary

DAG Manager GC targets only orphan Kafka/Redpanda queue topics that are no longer referenced by the Neo4j graph. Strategy quality scores, cross-world shadow detection, and alpha/research retention rules do not belong in this path.

| Queue tag | TTL | Grace | Action |
| --- | --- | --- | --- |
| `raw` | 7 days | 1 day | `drop` |
| `indicator` | 30 days | 3 days | `drop` |
| `sentinel` | 180 days | 30 days | `archive` then `drop` |

- `gc_interval_seconds` controls the scheduler cadence. The default is 60 seconds.
- When broker ingestion is at or above 80%, the collector halves the per-run batch size.
- When `gc_archive_bucket` is configured, sentinel archive writes use S3 `put_object`. The current archive payload is a lifecycle marker before deletion, not a full queue dump.
- If no archive client is configured, GC reports `archive_status=missing_client` and preserves the existing behavior of deleting the queue.
- If archive upload fails, GC does not delete that queue and reports an `archive_failed` skip.

### Manual Triggers and Reports

- HTTP: `POST /admin/gc-trigger` runs a full GC batch and returns `processed[]` plus `report`. The input `id` is a compatibility field and does not narrow the sweep.
- gRPC: `AdminService.Cleanup` also runs a full batch. The current proto response is empty, so operators that need the detailed report should use the HTTP endpoint.
- Scheduler: on server startup, `GCScheduler` periodically runs the same collector.

The `report` contains:

- `observed`: orphan queues seen by GC
- `candidates`: queues past TTL+grace
- `processed`: queue names actually dropped or archived
- `skipped`: skip reasons such as `within_grace`, `unknown_policy`, and `archive_failed`
- `actions`: counts by `drop`, `archive`, and `skip`
- `by_tag`: observed counts by tag

### ControlBus Events

When GC processes a queue, DAG Manager emits two payloads on the same ControlBus queue topic.

1. `QueueLifecycle`: lifecycle action, reason, and archive status for the deleted/archived queue
2. `QueueUpdated`: the post-GC queue set for the affected `(tag, interval)`

Gateway relays `QueueLifecycle` as a WebSocket `queue_lifecycle` event. `QueueUpdated` continues through the existing `queue_update` and `tagquery.upsert` reconciliation path.

### Artifact Boundary

DAG Manager `Artifact` nodes represent graph metadata and `USED_BY` references. Physical file TTL, deletion, and storage-tier movement are owned by the Feature Artifact Plane, Seamless materialization, or the SDK feature store. DAG Manager GC currently does not delete or archive artifact files, and cleanup reports do not include artifact candidates.

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
