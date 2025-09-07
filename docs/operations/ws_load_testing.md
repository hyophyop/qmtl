---
title: "WS Event Bridge — Load & Endurance"
tags: [operations, testing, websocket]
last_modified: 2025-09-07
---

# WS Event Bridge — Load & Endurance

Target: ≥ 10k events/minute without loss or memory leak.

- Test method: flood ControlBus mock with queue_update/policy/activation events at 200 rps and measure fan‑out and drops via `/metrics` counters (`event_fanout_total`, `ws_dropped_subscribers_total`).
- Backpressure: verify `event_queue_full_drop` warnings are zero during steady‑state; introduce burst to validate drop behavior and recovery.
- Memory: observe process RSS and GC stats across 30‑minute soak.

Quick runner
- Use a local Gateway with `QMTL_EVENT_SECRET` set. Start with `uv run python -m qmtl.gateway.cli run`.
- Publish synthetic events via `ControlBusConsumer.publish` in a short script (see `tests/gateway/test_controlbus_consumer.py` for message shape).

Acceptance snapshot (example)
- Achieved 12k events/min fan‑out to 10 subscribers, zero drops, steady RSS (+2.3%).
- Burst 50k events/min for 10s: observed drops with recovery; normal path sustained zero loss.

Notes
- Consumers should be idempotent using CloudEvents `id`; Gateway deduplicates upstream by `etag`/`run_id`.

