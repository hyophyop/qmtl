# Improvement Plan — 2025‑09‑04

This note tracks incremental hardening of WorldService service‑mode smoke tests and Gateway proxy behavior. See the normative specs in:

- [WorldService](worldservice.md)
- [Gateway](gateway.md)

Scope for the smoke suite:
- World CRUD registration and read‑back checks
- Gateway‑proxied decide/activation semantics (TTL, staleness, ETag)
- Evaluate/Apply round‑trip with `run_id` and live guard
- Event stream handshake via `/events/subscribe` and `/ws/evt`

Operational guidance:
- Tests MUST skip cleanly if endpoints are not provided in the environment
- Prefer idempotent probes and minimal payloads to avoid side effects

