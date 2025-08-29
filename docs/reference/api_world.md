---
title: "World API Reference — Proxied via Gateway"
tags: [reference, api, world]
author: "QMTL Team"
last_modified: 2025-08-29
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
  "effective_mode": "dryrun",
  "reason": "data_currency_ok&gates_pass&hysteresis",
  "as_of": "2025-08-28T09:00:00Z",
  "ttl": "300s",
  "etag": "w:crypto_mom_1h:v3:1724835600"
}
```
Schema: reference/schemas/decision_envelope.schema.json

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
  "etag": "act:crypto_mom_1h:abcd:long:42",
  "run_id": "7a1b4c...",
  "ts": "2025-08-28T09:00:00Z"
}
```
Schema: reference/schemas/activation_envelope.schema.json

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
{ "ok": true, "run_id": "..." }
```

### POST /events/subscribe
Returns an opaque event stream descriptor for real‑time control updates (activation/queues/policy).

Request
```json
{ "world_id": "crypto_mom_1h", "strategy_id": "...", "topics": ["activation", "queues"] }
```

Response
```json
{ "stream_url": "wss://gateway/ws/evt?ticket=...", "token": "<jwt>", "topics": ["activation"], "expires_at": "...", "fallback_url": "wss://gateway/ws/fallback" }
```
Initial message MUST be a full snapshot or include a `state_hash` per topic. Tokens are short‑lived JWTs with claims: `aud`, `sub`, `world_id`, `strategy_id`, `topics`, `jti`, `iat`, `exp`, `kid`.

## Error Semantics

- 404: unknown world
- 409: conflicting activation apply (etag/run_id mismatch)
- 503: degraded Gateway (temporary); clients should retry with backoff

{{ nav_links() }}
