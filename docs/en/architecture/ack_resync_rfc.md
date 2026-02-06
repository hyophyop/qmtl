---
title: "ACK/Gap Resync RFC (Draft)"
tags: [architecture, worldservice, controlbus, rfc]
author: "QMTL Team"
last_modified: 2026-02-06
status: draft
---

{{ nav_links() }}

# ACK/Gap Resync RFC (Draft)

## 1. Problem Statement

The Core Loop 2-Phase Apply path (`Freeze/Drain -> Switch -> Unfreeze`) already carries `ActivationUpdated.requires_ack=true`, but normative behavior is still partially ambiguous across documents.

- ACK semantics: Gateway receipt/apply acknowledgement vs. end-to-end acknowledgement including SDK/WebSocket consumers.
- Apply completion semantics: whether WorldService must hard-block completion on ACK stream convergence.
- Sequence gap handling: default timeout, retry, forced resync, and failure behavior.

This ambiguity can cause drift in freeze release timing, order-gate behavior, and incident recovery procedures.

## 2. Current State (Implementation-Aligned)

Related docs: [WorldService](worldservice.md), [ControlBus](controlbus.md), [Architecture](architecture.md)

- WorldService emits activation events with `phase`, `requires_ack`, and `sequence`.
- Gateway enforces per-`(world_id, run_id)` linear replay and publishes ACKs to `control.activation.ack`.
- In the current implementation, ACK means Gateway receipt/apply acknowledgement; a downstream SDK/WebSocket “second-stage ACK” is optional, not required.
- Current WorldService apply completion is not hard-blocked on ACK stream convergence.

## 3. Goals and Non-Goals

Goals
- Lock one explicit ACK meaning and align docs/runbooks to it.
- Define a default gap-resync policy for operational consistency.
- Provide a rollout path that strengthens guarantees without immediate breakage.

Non-Goals
- This RFC does not mandate immediate implementation of an end-to-end downstream ACK protocol.
- This RFC does not change ControlBus transport guarantees from at-least-once to exactly-once.

## 4. Options

### Option A: Gateway Single-Stage ACK + HTTP Resync Baseline

- Definition: ACK is fixed as Gateway in-order apply confirmation.
- Gap handling: timeout, then `state_hash` check + HTTP snapshot reconcile.
- Pros: closest to current behavior; low migration cost.
- Cons: downstream delivery guarantees remain outside ACK semantics.

### Option B: Two-Stage ACK (Includes Downstream Consumer ACK)

- Definition: unfreeze depends on both Gateway ACK and downstream SDK/WebSocket ACK convergence.
- Pros: stronger end-to-end confidence.
- Cons: significantly higher protocol/state/timeout complexity.

### Option C: Minimize ACK Semantics, Rely on Periodic Snapshot Reconcile

- Definition: de-emphasize sequence ACK and rely mainly on periodic full snapshot sync.
- Pros: simpler protocol surface.
- Cons: slower anomaly detection in freeze/unfreeze control windows.

## 5. Chosen Default Recommendation

The recommended default is **Option A**.

- ACK meaning: `requires_ack=true` means Gateway single-stage ACK.
- Gate rule: Gateway MUST NOT apply later events (especially unfreeze) before prior required sequences are applied/ACKed.
- Recommended default gap timeout: `activation_gap_timeout_ms=3000` (consumers SHOULD expose this as an operator-configurable setting).
- Recommended gap procedure:
  1. Keep order gates closed for the affected `(world_id, run_id)` stream.
  2. Probe divergence via `GET /worlds/{world_id}/activation/state_hash`.
  3. If needed, fetch snapshot via `GET /worlds/{world_id}/activation` and reconcile local state.
  4. Do not apply unfreeze until reconciliation succeeds.
- Apply completion semantics: keep current behavior; WorldService apply completion is not hard-blocked on ACK stream convergence, but operators SHOULD alert on prolonged ACK divergence.

## 6. Open Questions

- Q1. Should future apply completion partially depend on ACK convergence (subset of Option B)?
- Q2. Is 3000 ms the right default `activation_gap_timeout_ms` across environments?
- Q3. On forced resync failure, should standard behavior remain “freeze + operator intervention,” or include automatic rollback?
- Q4. What retention window is right for ACK topics (for example, 1h vs 24h)?

## 7. Migration and Rollout Plan

1. Contract lock (this change):
   - Align `architecture.md`, `worldservice.md`, and `controlbus.md`.
2. Observability hardening:
   - Add/track gap detection and reconcile success/failure metrics with ACK latency.
3. Feature-flag rollout:
   - Introduce `activation_resync_enforced` (default off) to phase in timeout-triggered forced resync.
4. Progressive deployment:
   - dev -> canary world -> full production.
5. Post-stabilization:
   - Revisit stronger apply/ACK coupling in a follow-up RFC if needed.

## 8. Test Plan

- Unit tests
  - sequence ordering, buffering, and deduplication.
  - gap timeout -> resync trigger logic.
- Integration tests
  - freeze/unfreeze with reordered, duplicated, and dropped events while enforcing order gates.
  - `state_hash` mismatch -> HTTP reconcile path.
- E2E tests
  - world apply flow validating unfreeze gating relative to ACK handling and safe fallback.
  - fault injection: ACK lag/loss, transient WS failures, and recovery behavior.

## 9. Compatibility and Risks

- Backward compatibility: Option A aligns with current behavior and avoids immediate breaking changes.
- Risk: overly aggressive gap timeout can cause excessive resync churn; tune with production metrics.

{{ nav_links() }}
