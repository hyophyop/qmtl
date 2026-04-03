---
title: "Architecture Runtime Reliability"
tags: [reference, architecture, reliability]
author: "QMTL Team"
last_modified: 2026-04-03
---

{{ nav_links() }}

# Architecture Runtime Reliability

This page collects the operational reliability notes, determinism checklist, and supplemental guidance that were split out of the [QMTL Normative Architecture](../architecture/architecture.md). Service boundaries and SSOT rules remain normative in the architecture documents; this page is the operator-facing companion.

## 1. Operational reliability proposals

1. **Once-and-only-once execution**  
   Use NodeID plus time bucket as the partition key, assign Kafka partition ownership via leases, and eliminate duplicate artifacts through a transactional commit log.
2. **Event-time watermarks and lateness tolerance**  
   Let NodeCache track a watermark, recompute within the allowed lateness window, and route excessive lateness into a separate policy path.
3. **Runtime fingerprinting**  
   Record Python, NumPy, and similar runtime versions as fingerprints and reuse caches only when `runtime_compat` allows it.
4. **Snapshot state hydration**  
   Persist NodeCache snapshots to Arrow/Parquet so restarts can hydrate state instead of paying the full warmup cost again.
5. **Schema Registry and CloudEvents alignment**  
   Keep data topics on Avro/Proto + Schema Registry and control topics on CloudEvents over Protobuf.

## 2. Determinism checklist

Use the following checks when validating global DAG consistency and high-reliability queue orchestration.

1. **Gateway <-> SDK CRC validation**  
   Verify that the Gateway-computed `node_id` and SDK-precomputed value match through `crc32`.
2. **NodeCache guardrails and GC**  
   Ensure slices beyond `period x interval` are evicted immediately and Arrow chunk zero-copy delivery is preserved.
3. **Kafka topic creation retries**  
   Follow the `CREATE_TOPICS -> VERIFY -> WAIT -> BACKOFF` loop and inspect broker metadata for near-name collisions.
4. **Sentinel traffic-shift verification**  
   Confirm Gateway and SDK converge on updated `traffic_weight` values within five seconds.
5. **TagQueryNode dynamic expansion**  
   Confirm Gateway emits `tagquery.upsert` for newly discovered `(tags, interval)` queues and Runner refreshes buffers automatically.
6. **Minor-schema buffering**  
   Reuse `schema_minor_change` nodes but force a full recompute after seven days.
7. **GSG canonicalization and SSA DAG lint**  
   Convert DAGs into canonical JSON plus SSA form and verify regenerated NodeIDs.
8. **Golden-signal SLOs and alerts**  
   Continuously track `diff_duration_ms_p95`, `nodecache_resident_bytes`, `sentinel_gap_count`, and submit→activation golden signals.
9. **Extreme-failure playbooks**  
   Cross-link runbooks and dashboards for full Neo4j outage, Kafka metadata corruption, and Redis AOF loss scenarios.
10. **Four-stage CI/CD gate**  
    Validate the chain of SSA lint, fast backtests, a 24h canary, 50% promotion, and one-command rollback.
11. **NodeID world exclusion**  
    Validate statically and dynamically that `world_id` never participates in NodeID inputs.
12. **TagQueryNode stability**  
    Verify that discovering additional queues does not change the NodeID when `query_tags`, `match_mode`, and `interval` are unchanged.

## 3. Observability and runbooks

- Gateway metrics:
  - `nodeid_checksum_mismatch_total{source="dag"}`
  - `nodeid_missing_fields_total{field,node_type}`
  - `nodeid_mismatch_total{node_type}`
  - `tagquery_nodeid_mismatch_total`
- Runbooks:
  - [Determinism Runbook](../operations/determinism.md)
  - [Core Loop Golden Signals](../operations/core_loop_golden_signals.md)
  - [ControlBus Operations](../operations/controlbus_operations.md)

If NodeID CRC or TagQuery mismatches rise, regenerate the DAG and rerun the Core Loop contract suite (`tests/e2e/core_loop`) before reopening the path.

## 4. Additional guidance

- Promotion policies and EvalKeys must always pin `dataset_fingerprint`; missing fingerprints should downgrade or reject applies.
- `observability.slo.cross_context_cache_hit` must stay at zero; halt execution until remediated if it ever rises.
- Policy bundles should spell out `share_policy`, edge overrides, and risk limits so the promotion pipeline remains auditable.
- Keep strategy scaffold changes aligned with the public `qmtl init` path and strategy workflow docs.

{{ nav_links() }}
