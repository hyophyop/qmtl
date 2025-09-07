---
title: "Migration: BLAKE3 NodeID"
tags: [migration]
author: "QMTL Team"
last_modified: 2025-09-07
---

{{ nav_links() }}

# Migration: BLAKE3 NodeID

The NodeID algorithm now uses BLAKE3 with a mandatory `blake3:` prefix and no longer includes `world_id`. Legacy SHA-based IDs are temporarily accepted but deprecated.

## Changes

- `compute_node_id` now returns `blake3:<digest>` computed from `(node_type, code_hash, config_hash, schema_hash)` without `world_id`.
- Legacy IDs can be produced via `compute_legacy_node_id` and are accepted by the Gateway during the deprecation window.

## Actions

- Remove `world_id` arguments from `compute_node_id` calls.
- Update stored NodeIDs to the new `blake3:` form.
- Plan migration away from `compute_legacy_node_id`; support will be removed in a future release.

{{ nav_links() }}
