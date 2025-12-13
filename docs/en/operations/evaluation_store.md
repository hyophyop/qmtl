# Evaluation Store Operations Guide

The WorldService Evaluation Store treats `EvaluationRun` records and their revisions as an **immutable (append-only) store**, so validation results, overrides, and policy versions remain traceable for operations and auditing.

## Storage Model (Summary)

- **Key**: `(world_id, strategy_id, run_id)`
- **Current snapshot**: `evaluation_runs` (one latest record)
- **Immutable history**: `evaluation_run_history` (append a revision on every update)
  - Override updates, extended validation enrichments, and other updates are **accumulated in history**.

## Immutability Principles

- For a given `(world_id, strategy_id, run_id)`, **past evaluation outputs must not be overwritten.**
  - The latest snapshot may change, but every change must be appended to `evaluation_run_history`.
- When re-evaluating, create a **new `run_id`**.
- For operations/auditing, `override_status=approved` must include reason/actor/timestamp metadata.

## API Contract (Read/History/Override)

Key endpoints:

- List: `GET /worlds/{world_id}/strategies/{strategy_id}/runs`
- Get: `GET /worlds/{world_id}/strategies/{strategy_id}/runs/{run_id}`
- History: `GET /worlds/{world_id}/strategies/{strategy_id}/runs/{run_id}/history`
- Override: `POST /worlds/{world_id}/strategies/{strategy_id}/runs/{run_id}/override`
- Invariants report: `GET /worlds/{world_id}/validations/invariants`

Compatibility guidelines:

- Schema changes must be **additive only** (no meaning changes or removals of existing fields).
- `metrics` should follow the `returns/sample/risk/robustness/diagnostics` blocks, and
  unknown fields should be ignored (or preserved via `diagnostics.extra_metrics`).
- For large payloads (e.g., covariance, realized returns, stress outputs), prefer **offload(ref)** patterns.

## Retention Policy (Recommended)

Recommended defaults:

- `evaluation_runs`: keep the latest snapshot long-term (deleted when the world is deleted)
- `evaluation_run_history`: retain for at least **180 days** (extend to 1 year if audit/regression needs require it)

Purge guidance:

- Only purge history records that are beyond the retention period (as required for capacity/PII/compliance).
- Purging can weaken auditability of an append-only store, so require an operational approval process.

## Operational Playbook (Examples)

- Regression / audit:
  - Inspect revision-by-revision changes via the `/history` endpoint
  - Pin policy impact analysis via `scripts/policy_diff_batch.py`
- Overrides:
  - Approved overrides must include reason/actor/timestamp, and
    keep the run’s `/history` for later review.

