---
title: "Migration: BLAKE3 NodeID"
tags: [migration]
author: "QMTL Team"
last_modified: 2025-09-07
---

{{ nav_links() }}

# Migration: BLAKE3 NodeID

The NodeID algorithm uses BLAKE3 with a mandatory `blake3:` prefix and must not include `world_id`. Legacy SHA-based IDs are no longer accepted and the helper has been removed.

## Changes

- `compute_node_id` returns `blake3:<digest>` computed from `(node_type, code_hash, config_hash, schema_hash)` without `world_id`.
- The legacy helper `compute_legacy_node_id` has been removed; Gateways reject non-canonical IDs.

## Actions

- Ensure all code paths use `compute_node_id` exclusively.
- Migrate any stored NodeIDs to the canonical `blake3:` form.
- Remove any references to `compute_legacy_node_id` in your codebase.
- Update DAG serialization to include `config_hash` alongside `code_hash` and `schema_hash` so Gateway validation can recompute canonical IDs.

{{ nav_links() }}
