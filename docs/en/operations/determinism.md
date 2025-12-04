---
title: "Determinism Runbook — NodeID/TagQuery mismatch response"
tags: [operations, determinism, runbook]
author: "QMTL Team"
last_modified: 2025-12-06
---

{{ nav_links() }}

# Determinism Runbook — NodeID/TagQuery mismatch response

## What to watch
- Gateway metrics:
  - `nodeid_checksum_mismatch_total{source="dag"}`: submitted `node_ids_crc32` differs from the recomputed value.
  - `nodeid_missing_fields_total{field,node_type}`: canonical NodeID inputs missing.
  - `nodeid_mismatch_total{node_type}`: submitted `node_id` differs from `compute_node_id`.
  - `tagquery_nodeid_mismatch_total`: TagQueryNode-specific mismatch counter.
  - `worlds_compute_context_downgrade_total{reason}`, `strategy_compute_context_downgrade_total{reason}`: default-safe downgrades when WS decisions are missing/stale or `as_of` is absent.
- SDK metrics:
  - `tagquery_update_total{outcome,reason}`: TagQuery queue update events classified as `applied`, `deduped`, `unmatched` (no registered node), or `dropped` (`missing_interval|missing_tags|invalid_spec`).
  - `nodecache_resident_bytes{node_id}`: DAG Manager/SDK NodeCache GC should keep this flat or falling after GC; monotonic growth hints at stale cache.
- When alerts fire, capture the offending DAG/queue_map so the submission can be replayed locally.

## Immediate actions
1) **CRC mismatch (`nodeid_checksum_mismatch_total`)**
   - Decode the DAG JSON and recompute `node_ids_crc32` locally (`qmtl.foundation.common.crc32_of_list`).
   - Ensure SDK- and Gateway-computed node_ids match, regenerate CRC, and resubmit.

2) **Missing fields (`nodeid_missing_fields_total`)**
   - Read the missing field labels from metrics/logs and regenerate the DAG with the latest SDK.
   - Verify `code_hash`, `config_hash`, `schema_hash`, and `schema_compat_id` are present for every node. For TagQueryNode, `interval` and at least one `tag` are now required to pass determinism checks.

3) **NodeID mismatch (`nodeid_mismatch_total`)**
   - Recompute with `compute_node_id` and compare with the submitted value.
   - For TagQueryNode, ensure `query_tags` are sorted/deduped and both `match_mode` and `interval` are present before recalculating.

4) **TagQuery update drops (`tagquery_update_total{outcome="dropped"|"unmatched"}`)**
   - `missing_interval|missing_tags`: regenerate the DAG/WS TagQuery payloads with canonical tags and interval; queue updates are being rejected before reaching nodes.
   - `no_registered_node`: check for NodeID drift or TagQuery spec mismatch between the DAG and SDK registration; reconcile and resubmit.

5) **ComputeContext downgrade spikes (`worlds_compute_context_downgrade_total` / `strategy_compute_context_downgrade_total`)**
   - Check if WS `decide`/`activation` responses are slow or missing; verify WS health/TTL.
   - Confirm client submission metadata includes `as_of`/`dataset_fingerprint`. If missing, compute-only downgrades are expected (default-safe contract).
   - If responses are marked stale (ETag/TTL expired), inspect WS cache/proxy/connectivity and restart WS if needed.

6) **NodeCache GC/memory growth (`nodecache_resident_bytes`)**
   - If monotonic or not dropping after GC, NodeCache may be retaining old nodes. Restart DAG Manager/SDK to clear caches and confirm NodeID CRC matches.
   - If it keeps climbing post-GC, revisit NodeID determinism rules and the contract tests (`tests/e2e/core_loop`) to lock the rules again.

## Recovery checks
- Resubmit with the fixed DAG and ensure the counters stop increasing.
- Run the Core Loop contract suite to confirm there are no regressions:

```bash
CORE_LOOP_STACK_MODE=inproc uv run -m pytest -q tests/e2e/core_loop -q
```

## References
- Design baseline: `docs/en/architecture/architecture.md` §7 Determinism & Operational Checklist.
- World/domain isolation checks: `tests/e2e/test_world_isolation.py`.
- Dashboards: plot `nodeid_checksum_mismatch_total`, `nodeid_missing_fields_total`, `nodeid_mismatch_total`, `tagquery_nodeid_mismatch_total`, `tagquery_update_total`, `worlds_compute_context_downgrade_total`, and `nodecache_resident_bytes` together to surface drift, downgrade, and GC issues.
