---
title: "WS-only Resilience & Recovery"
tags: []
author: "QMTL Team"
last_modified: 2025-09-07
---

{{ nav_links() }}

# WS-only Resilience & Recovery

This guide explains how QMTL handles WebSocket‑only paths for queue updates
and control events, and how duplicate processing is avoided after reconnects.

## Behavior overview

- Centralized manager: the SDK’s TagQueryManager performs initial tag→queue
  resolution via HTTP and subscribes to Gateway WebSocket updates to track
  dynamic changes.
- Reconnection: the SDK WebSocket client uses bounded backoff with heartbeat
  pings to detect broken connections and heal automatically.
- Backpressure: the Gateway WS hub applies a simple policy to drop newest
  messages when buffers are full, relying on upstream idempotency.

## Duplicate prevention

QMTL avoids duplicate processing through layered idempotency:

- SDK NodeCache produces an `input_window_hash` used by the Gateway commit‑log
  path to deduplicate replays.
- The Gateway’s commit‑log consumer drops duplicate records by message key
  within a sliding window.
- The WS hub guards against duplicate CloudEvent IDs emitted during retries.

As a result, after a disconnect and recovery, nodes resume without duplicate
compute executions for the same `(node_id, bucket_ts, input_window_hash)`.

## Operational guidance

- Favor short timeouts in test and staging (`QMTL_TEST_MODE=1`) to surface
  reconnection paths quickly.
- For long‑running soaks, monitor:
  - `gateway_ws_duplicate_drop_total` (if enabled) and commit‑log duplicate
    counters
  - `dagclient_breaker_*` / `kafka_breaker_*` gauges for circuit state
- Use `Runner.session(...)` in tests to ensure TagQueryManager and background
  tasks are cleaned up on exit.

{{ nav_links() }}

