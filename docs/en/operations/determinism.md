---
title: "Determinism Runbook — NodeID/TagQuery mismatch response"
tags: [operations, determinism, runbook]
author: "QMTL Team"
last_modified: 2025-09-01
---

{{ nav_links() }}

# Determinism Runbook — NodeID/TagQuery mismatch response

## What to watch
- Gateway metrics:
  - `nodeid_checksum_mismatch_total{source="dag"}`: submitted `node_ids_crc32` differs from the recomputed value.
  - `nodeid_missing_fields_total{field,node_type}`: canonical NodeID inputs missing.
  - `nodeid_mismatch_total{node_type}`: submitted `node_id` differs from `compute_node_id`.
  - `tagquery_nodeid_mismatch_total`: TagQueryNode-specific mismatch counter.
- When alerts fire, capture the offending DAG/queue_map so the submission can be replayed locally.

## Immediate actions
1) **CRC mismatch (`nodeid_checksum_mismatch_total`)**
   - Decode the DAG JSON and recompute `node_ids_crc32` locally (`qmtl.foundation.common.crc32_of_list`).
   - Ensure SDK- and Gateway-computed node_ids match, regenerate CRC, and resubmit.

2) **Missing fields (`nodeid_missing_fields_total`)**
   - Read the missing field labels from metrics/logs and regenerate the DAG with the latest SDK.
   - Verify `code_hash`, `config_hash`, `schema_hash`, and `schema_compat_id` are present for every node.

3) **NodeID mismatch (`nodeid_mismatch_total`)**
   - Recompute with `compute_node_id` and compare with the submitted value.
   - For TagQueryNode, ensure `query_tags` are sorted/deduped and both `match_mode` and `interval` are present before recalculating.

## Recovery checks
- Resubmit with the fixed DAG and ensure the counters stop increasing.
- Run the Core Loop contract suite to confirm there are no regressions:

```bash
CORE_LOOP_STACK_MODE=inproc uv run -m pytest -q tests/e2e/core_loop -q
```

## References
- Design baseline: `docs/en/architecture/architecture.md` §7 Determinism & Operational Checklist.
- World/domain isolation checks: `tests/e2e/test_world_isolation.py`.
