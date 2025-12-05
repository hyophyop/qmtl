# WebSocket Load & Endurance

Gateway’s WS bridge relays ControlBus updates to SDKs. This page documents the target rates, bench method, and operational knobs.

The Core Loop golden-signal dashboard uses these metrics to track the WS → Gateway/SDK propagation SLO; see [core_loop_golden_signals.md](core_loop_golden_signals.md) for panel placement.

## Targets

- Sustained rate: ≥ 10k events/min (≈167 msg/s) without loss on the normal path.
- Per-topic ordering: preserved best-effort within the Gateway fan-out loop.
- Backpressure: engages under overload; newest events may be dropped, with counters incremented.

## Bench Method (dev box)

- Subscribers: 100 in-process dummy websockets connected to `/ws/evt` with a valid token.
- Topics: `activation` and `queue`.
- Load: 180 msg/s for 5 minutes, then 600 msg/s for 1 minute.
- Metrics to watch:
  - `event_relay_events_total{topic="activation"}` grows linearly at nominal rate.
  - `event_relay_dropped_total{topic}` remains 0 at ≤180 msg/s; rises under 600 msg/s.
  - `ws_subscribers{topic}` matches expected counts; `ws_dropped_subscribers_total` stays 0.

## Operational Notes

- Idempotency: CloudEvents `id` is treated as an idempotency key. The WS hub keeps a fixed-size window (10k ids) to drop duplicates during reconnect/retry.
- Backpressure policy: internal fan-out queue is bounded (default 10k). On full queue, the newest event is dropped and a structured log `event_queue_full_drop` is emitted.
- Ordering: Per-topic ordering is preserved best-effort in a single-process hub. If cross-partition reordering is possible upstream, consumers should reassemble by `time` or the hub-assigned monotonic `seq_no` now included in each CloudEvent.
- Scoping: Server-side filters apply `world_id` and optional `strategy_id` from the JWT to avoid leaking events across worlds.

### Recovery & Idempotency

- WS-only runners recover from temporary disconnects without duplicate state changes:
  - Server drops duplicate CloudEvents by `id` within a sliding window.
  - SDK drops duplicate `queue_update` payloads per `(tags, interval, match_mode)` key when the effective queue set is unchanged.
- Consumers should treat WS messages as level-triggered updates rather than strictly edge-triggered; on reconnection, ignore redundant updates and proceed.

### Rate limiting

- Per-connection rate limiting is available via a simple token bucket in the WS hub. It is disabled by default. To enable it, set `gateway.websocket.rate_limit_per_sec` in the Gateway YAML (tokens/messages per second), e.g. `gateway.websocket.rate_limit_per_sec: 200`.

## Troubleshooting

- Frequent drops: Increase queue size or lower publish rate; verify consumer acks are timely.
- Memory growth: Confirm that subscribers are disconnecting cleanly; check `ws_dropped_subscribers_total` and GC logs.
- Auth failures: Inspect `ws_auth_failed` and `ws_token_refreshed` structured logs; validate JWKS exposure at `/events/jwks`.
