---
title: "TagQuery Reference"
tags: []
author: "QMTL Team"
last_modified: 2025-09-23
---

{{ nav_links() }}

# TagQuery Reference

- Overview: `TagQueryNode` selects upstream queues by tag set and interval. The Runner wires a per‑strategy `TagQueryManager` that resolves the initial queue list and applies live updates via WebSocket.
- Endpoint: Gateway exposes `GET /queues/by_tag` with params `tags` (comma‑separated), `interval` (seconds), `match_mode` (`any`|`all`), and optional `world_id`.
- Matching: `match_mode=any` selects queues containing any tag; `all` requires all tags. Tags are normalized (whitespace trimmed, empties removed) and sorted for stable keys.
- Normalization: Gateway returns an array of descriptor objects:
  - `{"queue": "<id>", "global": <bool>}`. Entries with `global=true` are ignored by the SDK for node execution.

## Tag/Interval & Namespace Contract

- Tags are attached to ComputeNodes/Queues via the DAG Manager (e.g., strategy nodes emitting price bars tagged with asset class, venue, or factor family).
- The `interval` parameter is the queue interval in **seconds** and must match the node’s configured interval; mismatched intervals yield no results.
- When `world_id` is provided and topic namespaces are enabled, Gateway uses `{world_id}.{execution_domain}.<topic>` as the namespace prefix (see `DagManagerClient.get_queues_by_tag`).  
  This ensures TagQueryNode lookups stay isolated per world/domain while still using global tags.

The tag/interval/namespace mapping is the same regardless of whether queues are fed by Seamless presets or other sources; Seamless worlds typically seed queues whose tags/intervals align with the `world.data.presets[].universe` and `interval_ms` fields.

## Runner Integration

- Boot sequence: `Runner.submit(..., world=..., mode=...)` attaches `TagQueryManager` via the Gateway bootstrap path, applies the `queue_map` to nodes, and calls `resolve_tags()` once before starting live subscriptions.
- Live updates: After boot, `TagQueryManager.start()` subscribes to `/events/subscribe` and periodically reconciles via `GET /queues/by_tag` to heal divergence.
- Offline/backtest: When using `Runner.submit(..., mode="backtest")` or when Gateway/Kafka are unavailable, `resolve_tags(offline=True)` hydrates queue mappings from a local cache file (`.qmtl_tagmap.json` by default). If no snapshot exists, nodes fall back to an empty queue set and remain compute-only until data is fed.

## Caching & Determinism

- Each resolve call writes a snapshot of tag→queue mappings to `.qmtl_tagmap.json` (override via `cache.tagquery_cache_path`).
- The snapshot stores a CRC32 checksum to detect corruption and ensure dry-runs and backtests replay the exact queue set.

## Timing & Timeouts

- HTTP timeout: `qmtl.runtime.sdk.runtime.HTTP_TIMEOUT_SECONDS` (default 2.0s; 1.5s in tests).
- WebSocket receive timeout: `qmtl.runtime.sdk.runtime.WS_RECV_TIMEOUT_SECONDS` (default 30s; 5s in tests).
- Reconcile poll interval: `qmtl.runtime.sdk.runtime.POLL_INTERVAL_SECONDS` (default 10s; 2s in tests).
- Test mode: Set `test.test_mode: true` in `qmtl.yml` to activate conservative time budgets for CI and local tests.

{{ nav_links() }}
