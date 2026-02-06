---
title: "World API Reference — Proxied via Gateway"
tags: [reference, api, world]
author: "QMTL Team"
last_modified: 2026-02-06
---

{{ nav_links() }}

# World API Reference — Proxied via Gateway

Gateway proxies WorldService endpoints for SDKs and tools. This page lists the key endpoints and normative envelopes. See also: docs/world/world.md §12 for examples.

## Authentication

- External callers authenticate to Gateway (JWT). Gateway authenticates/authorizes to WorldService using service credentials and forwards identity scopes.

## Endpoints

### GET /worlds/{id}
Returns world metadata and default policy version.

### GET /worlds/{id}/decide
Returns a DecisionEnvelope for the specified `as_of`.

Query params
- `as_of` (optional ISO‑8601). If omitted, server time is used.

Response (DecisionEnvelope)
```json
{
  "world_id": "crypto_mom_1h",
  "policy_version": 3,
  "effective_mode": "validate",
  "reason": "data_currency_ok&gates_pass&hysteresis",
  "as_of": "2025-08-28T09:00:00Z",
  "ttl": "300s",
  "etag": "w:crypto_mom_1h:v3:1724835600"
}
```
Schema: reference/schemas/decision_envelope.schema.json

### POST /worlds/{id}/decisions
Replaces the active strategy set for the world. The payload is a `DecisionsRequest`, a lightweight contract that mirrors `qmtl.services.worldservice.schemas.DecisionsRequest`.

Request (DecisionsRequest)
```json
{
  "strategies": ["alpha", "beta"]
}
```

Semantics

- `strategies` must be a list of non-empty strings. Entries are deduplicated after trimming whitespace while preserving their original order.
- Supplying an empty list clears all active strategy decisions for the world.
- The response echoes the persisted strategy list using the same envelope as `/worlds/{id}/bindings`.

Response (BindingsResponse)
```json
{
  "strategies": ["alpha", "beta"]
}
```

Schema: reference/schemas/decisions_request.schema.json

### GET /worlds/{id}/activation
Returns activation for a strategy/side.

Query params
- `strategy_id` (string), `side` ("long"|"short")

Response (ActivationEnvelope)
```json
{
  "world_id": "crypto_mom_1h",
  "strategy_id": "abcd",
  "side": "long",
  "active": true,
  "weight": 1.0,
  "freeze": false,
  "drain": false,
  "effective_mode": "paper",
  "execution_domain": "backtest",
  "compute_context": {
    "world_id": "crypto_mom_1h",
    "execution_domain": "backtest",
    "as_of": null,
    "partition": null,
    "dataset_fingerprint": null,
    "downgraded": true,
    "downgrade_reason": "missing_as_of",
    "safe_mode": true
  },
  "etag": "act:crypto_mom_1h:abcd:long:42",
  "run_id": "7a1b4c...",
  "ts": "2025-08-28T09:00:00Z"
}
```
`effective_mode` carries the WorldService policy string and remains
backwards-compatible (`validate|compute-only|paper|live|shadow`). Gateway also
accepts legacy `sim` values as a `paper` alias during augmentation. The
Activation relay and augmentation contract (runtime):
- Gateway adds derived `execution_domain` and `compute_context` when it materializes activation payloads via `GET /worlds/{id}/activation`, activation bootstrap frames emitted by `/events/subscribe`, and ControlBus `activation_updated` relays before WebSocket fan-out.
- Mapping used in that augmentation path is `validate → backtest`, `compute-only → backtest`, `paper|sim → dryrun`, `live → live`, `shadow → shadow`.
- Activation envelopes do not include `as_of`, so safe-mode evaluation can downgrade modes that map to `backtest/dryrun` (`validate|compute-only|paper|sim`) to `execution_domain=backtest` (`downgraded=true`, `downgrade_reason=missing_as_of`, `safe_mode=true`). This metadata is not limited to `paper`. `shadow` is not downgraded by the missing-`as_of` guard.
- If the activation payload lacks `effective_mode`, Gateway fail-closes to `execution_domain=backtest` and sets `safe_mode=true`, `downgraded=true`, `downgrade_reason=decision_unavailable`.
- For ControlBus `activation_updated`, Gateway recomputes augmentation from `effective_mode`; upstream-provided `execution_domain`/`compute_context` fields are overwritten by canonical augmentation output.
- For queue/tag relays, `queue_update` forwards `world_id`/`execution_domain` when present, while `tagquery.upsert` payloads do not carry these fields (Gateway only uses `execution_domain` in the dedupe key `(tags, interval, execution_domain)`).
- SDKs treat `effective_mode`/`execution_domain` as read-only annotations for local state/metrics; clients MUST NOT override backend decisions or mutate execution behavior from those fields.
Stale activation fail-safe invariants (cache response path):
- When Gateway serves a stale activation (`X-Stale: true`, `Warning: 110 - Response is stale`), it enforces fail-closed values: `active=false`, `weight=0.0`, `effective_mode=compute-only`, `execution_domain=backtest`.
- Rationale: stale cache state cannot prove current activation safety, so order-enable paths must stay closed and converge to compute-only behavior.
Schema: reference/schemas/activation_envelope.schema.json

### GET /worlds/{id}/{topic}/state_hash
Returns a `state_hash` for the given topic so clients can check for divergence before requesting a full snapshot.

Example: `/worlds/{id}/activation/state_hash`

Response
```json
{ "state_hash": "blake3:..." }
```

### POST /worlds/{id}/evaluate
Evaluates current policy and returns a plan. Read‑only; does not change activation.

Request
```json
{ "as_of": "2025-08-28T09:00:00Z" }
```

Response (example)
```json
{ "topk": ["s1","s2"], "promote": ["s1"], "demote": ["s9"], "notes": "..." }
```

### POST /worlds/{id}/apply
Applies an activation plan using 2‑Phase apply.

Request
```json
{ "run_id": "...", "plan": { "activate": ["s1"], "deactivate": ["s9"] } }
```

Response
```json
{
  "ok": true,
  "run_id": "...",
  "active": ["s1", "s2"],
  "phase": "completed"
}
```

- `ok` defaults to `true` and only flips to `false` if the apply run aborts.
- `active` always echoes the persisted strategy list after the apply completes (empty when nothing is active).
- `phase` is optional; when present it reflects the final stage (`completed`, `rolled_back`, etc.). Intermediate polling may observe `phase` transitions such as `freeze` or `switch`.

### POST /events/subscribe
Returns an opaque event stream descriptor for real‑time control updates (activation/queues/policy).

Request
```json
{ "world_id": "crypto_mom_1h", "strategy_id": "...", "topics": ["activation", "queues"] }
```

Response
```json
{ "stream_url": "wss://gateway/ws/evt?ticket=...", "token": "<jwt>", "topics": ["activation"], "expires_at": "...", "fallback_url": "wss://gateway/ws" }
```
Initial message MUST be a full snapshot or include a `state_hash` per topic. Tokens are short‑lived JWTs with claims: `aud`, `sub`, `world_id`, `strategy_id`, `topics`, `jti`, `iat`, `exp`. Key ID (`kid`) is conveyed in the JWT header.

Heartbeats and acknowledgements
- Clients should send periodic heartbeats. Sending any message counts as a heartbeat; optionally send `{ "type": "ack", "last_id": "<cloudevents id>" }` to acknowledge delivery.
- Gateway logs connection/auth failures, retries, and normal closes with structured fields and exposes counters under `/metrics`.

Scope filtering
- Subscriptions are scoped by `world_id` and `topics`. The WS bridge applies scope filters server‑side so clients receive only events for the authorized world.

Backpressure and rate limits
- Gateway applies backpressure to its internal fan‑out queue. Under sustained overload, newest messages may be dropped and a counter is incremented. Normal operating conditions target zero drops.
- Clients should implement retries and idempotent handling using CloudEvents `id` (idempotency key) and `correlation_id`.

Ordering and loss guarantees
- Events preserve per‑topic ordering on best effort. If reordering is possible (e.g., across partitions), consumers must reassemble by `time` or apply a monotonic `seq_no` if present. Gateway documents no loss on the normal path; snapshots/state hashes enable recovery.

### GET /events/jwks
Returns a JWKS document describing the current and previous signing keys for event stream tokens.

Response (example)
```json
{
  "keys": [
    { "kty": "oct", "use": "sig", "alg": "HS256", "kid": "old", "k": "czE=" },
    { "kty": "oct", "use": "sig", "alg": "HS256", "kid": "new", "k": "czI=" }
  ]
}
```

## Error Semantics

- 404: unknown world
- 409: conflicting activation apply (etag/run_id mismatch)
- 503: degraded Gateway (temporary); clients should retry with backoff

{{ nav_links() }}

### GET /events/schema
Returns JSON Schemas for WebSocket CloudEvent envelopes per topic.

Response (example keys)
```json
{ "queue_update": { "$schema": "https://json-schema.org/...", ... }, "activation_updated": { ... } }
```
