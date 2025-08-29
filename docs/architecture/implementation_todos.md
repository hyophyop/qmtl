# Architecture–Code Sync TODOs (Aug 2025)

This document lists concrete implementation tasks required to align the current codebase with the updated architecture documents.

Related specs:
- Architecture Overview: architecture.md
- Gateway: gateway.md
- DAG Manager: dag-manager.md
- WorldService: worldservice.md
- ControlBus: controlbus.md

---

## High Priority (P0)

- Worlds Proxy API in Gateway:
  - Implement GET "/worlds/{id}/decide" and "/worlds/{id}/activation" with TTL/etag caching and safe fallbacks when stale. Enforce live guard (header "X-Allow-Live: true" or CLI "--allow-live").
  - Implement POST "/worlds/{id}/evaluate" (read-only) and POST "/worlds/{id}/apply" (2-phase apply with "run_id", idempotent). Forward caller identity (JWT subject/claims) to WorldService.
  - Config: add "worldservice_url", timeouts/retry budgets separate from DAG Manager. Metrics: cache hit ratio, proxy latency p95.
  - Spec refs: architecture/gateway.md §S6; architecture/worldservice.md §2–§6; reference/api_world.md; reference/schemas.md.

- Event Stream Descriptor endpoint:
  - Implement POST "/events/subscribe" -> returns "{ stream_url, token, topics, expires_at, fallback_url }". Generate short-lived JWT (claims: "aud=controlbus", "sub", "world_id", "strategy_id", "topics", "jti", "iat", "exp", "kid").
  - Provide WS entrypoint (e.g., "wss://…/ws/evt") that relays ControlBus events to clients; first message per topic MUST be a full snapshot or include "state_hash".
  - Spec refs: architecture/gateway.md §S6, architecture/controlbus.md §7, reference/api_world.md.

- ControlBus subscription in Gateway:
  - Subscribe to "control.activation" (ActivationUpdated), "control.policy" (PolicyUpdated), "control.queues" (QueueUpdated). Deduplicate via "etag"/"run_id". Partition ordering per key.
  - Bridge to WebSocketHub broadcast. Maintain per-topic last "etag" and export lag/skew metrics.
  - Config: "controlbus" section (brokers/DSN, topics, consumer group). Backoff and at-least-once semantics.
  - Spec refs: architecture/controlbus.md §0–§3; architecture/dag-manager.md §3-B.

- Deterministic NodeID verification in Gateway:
  - Compute NodeID = SHA-256("node_type, code_hash, config_hash, schema_hash") with SHA-3 fallback on collision; verify against SDK-supplied IDs before Diff. Return HTTP 400 on mismatch.
  - Replace the current CRC32-of-node-ids check or keep it as a lightweight early guard in addition to NodeID recompute.
  - Spec refs: architecture/architecture.md §3; architecture/gateway.md §S4; architecture/dag-manager.md §1.3.

---

## Medium Priority (P1)

- WebSocket integration cleanup:
  - Expose a stable WS path under FastAPI (e.g., "/ws" and "/ws/evt") instead of running an ad-hoc server. Ensure compatibility with "qmtl.sdk.ws_client.WebSocketClient" default "/ws" path.
  - Add broadcasts for ActivationUpdated and PolicyUpdated in "WebSocketHub".
  - Provide "fallback_url" and reconnection guidance (HTTP reconcile to "/worlds/{id}/activation" and "/queues/by_tag").

- Metrics & observability additions:
  - "sentinel_skew_seconds" (after weight updates) and ControlBus consumer lag per topic.
  - World proxy metrics: "world_decide_latency_ms_p95", "world_activation_cache_hit_ratio", proxy error rates.
  - Gateway event relay metrics: fanout rate, dropped subscribers, partition skew.

- Circuit budgets & degradation policies (WorldService):
  - Add independent timeouts/retries for WorldService proxy calls (defaults: WS 300 ms 2x; DM 500 ms 1x). Integrate with existing "AsyncCircuitBreaker". Surface states in "/status".

- Backward-compat callbacks:
  - Keep "/callbacks/dag-event" handling but migrate payloads to the versioned ControlBus envelopes ("ActivationUpdated", "PolicyUpdated", "QueueUpdated").

---

## Low Priority (P2)

- Legacy "/queues/watch":
  - Endpoint retained for compatibility; emits ``Deprecation`` header pointing to ``/events/subscribe``.
  - SDKs should reconcile via ``/queues/by_tag`` over HTTP if the event stream is unavailable.

- World initial snapshot semantics:
  - Add optional HTTP endpoints for "state_hash" probe to avoid full snapshot when unchanged.

- Security hardening:
  - JWT key rotation and JWKS for delegated WS; world-scope RBAC claims pass-through; audit correlation IDs for all proxied calls and relayed events.

---

## Affected Code (initial mapping)

- Gateway additions/changes:
  - "qmtl/gateway/api.py": add "/worlds/*", "/events/subscribe", integrate WS endpoints; identity propagation and live guard.
  - "qmtl/gateway/ws.py": extend to ActivationUpdated/PolicyUpdated; integrate with FastAPI lifecycle.
  - "qmtl/gateway/config.py": add "worldservice_url", "controlbus" settings, timeouts/retries.
  - "qmtl/gateway/dagmanager_client.py": keep; ensure NodeID recompute occurs before Diff (new helper module if needed).
  - New: "qmtl/gateway/controlbus_consumer.py" (subscribe, dedupe, metrics) — config-driven; optional in dev.
  - New: "qmtl/common/nodeid.py" (deterministic NodeID computation, SHA-3 fallback).

- DAG Manager (alignment):
  - Ensure QueueUpdated events are also published to ControlBus in addition to HTTP callback (already documented as preferred path).

- SDK (follow-up, separate PR):
  - Migrate "TagQueryManager" to use "/events/subscribe" descriptor when available; keep "/queues/by_tag" + "/queues/watch" as fallback.

---

## Test Plan (summary)

- Contract tests for Decision/Activation envelopes using JSON Schemas in "docs/reference/schemas/".
- Gateway proxy tests: caching TTL semantics, live-guard behaviour, identity propagation headers.
- ControlBus bridge tests: at-least-once delivery, per-key ordering, dedupe via "etag"/"run_id".
- WebSocket throughput: >= 500 msg/s sustained; initial snapshot or "state_hash" presence.
- NodeID recompute: mismatch -> 400; match -> call Diff.

---

## Already Compliant (no action)

- Strategy ingest & FSM with Redis + DB mirror; idempotent queue locking ("SETNX lock:{id}" with TTL).
- VersionSentinel insertion with "insert_sentinel" config and "--no-sentinel" flag.
- Tag query resolution via "/queues/by_tag" with "match_mode" (and "match" alias) and streaming updates bridged to SDK.
- Degradation manager and local fallback queue for DAG outages; "/status" health caching.
- Sentinel traffic ratio metric "gateway_sentinel_traffic_ratio{sentinel_id=...}".
