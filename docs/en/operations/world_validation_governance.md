# World Validation Governance (Override Re-review)

This document operationalizes [World Validation Architecture (icebox, reference-only)](../design/icebox/world_validation_architecture.md) §12.3 (Invariant 3) by standardizing the **approved override re-review queue, deadlines, and SLA**.

## Concepts (Summary)

- **Override (approved)**: An operational/risk-approved exception where `summary.status` is not `"pass"`.
- **Invariant 3**: Approved overrides must be aggregated into a dedicated list and re-reviewed within a fixed window (e.g., 30/90 days).

## Required fields

Approved overrides must record the following fields.

- `override_reason`: approval reason
- `override_actor`: approver identity
- `override_timestamp`: approval timestamp (UTC ISO8601)

## Re-review window (defaults)

Current defaults in code:

- `stage=live`: **30 days**
- `risk_profile.tier=high` AND `client_critical=true`: **30 days**
- Otherwise: **90 days**

## Queue generation (entrypoints)

- Storage-based (recommended):  
  `uv run python scripts/generate_override_rereview_report.py --output override_queue.md`
- GitHub Actions schedule (recommended):  
  `.github/workflows/override-rereview-queue.yml` (auto-skips if secrets are missing + uploads report artifacts)
- API-based (per world):  
  `GET /worlds/{world_id}/validations/invariants` → inspect `approved_overrides`

Each `approved_overrides` entry includes `review_due_at`, `review_overdue`, and `missing_fields`.

## Operational workflow (brief)

1) Generate the queue daily/weekly and triage entries with `review_overdue=true` or non-empty `missing_fields`.  
2) Apply a decision:
   - remove the override (normalize), or
   - renew the override (update reason/actor/timestamp) and record follow-ups
3) For recurring overrides, feed back into policy/rules and investigate root causes (data, rebalancing, risk signals, rule design).

## Ex-post Failure Management (pass-then-fail rate)

An ex-post failure is a case classified as “validation passed, but in live operations this was a clear failure that should have been avoided”.

- Storage location (SSOT): `EvaluationRun.summary.ex_post_failures` (append-only log)
  - Fields: `case_id`, `status=candidate|confirmed`, `category`, `reason_code`, `severity`, `evidence_url`, `actor`, `recorded_at`, `source`, `notes`
  - taxonomy (examples):
    - `category`: `risk_breach`, `performance_failure`, `liquidity_failure`, `data_issue`, `ops_incident`
    - `severity`: `critical|high|medium|low`
- Recording API:
  - `POST /worlds/{world_id}/strategies/{strategy_id}/runs/{run_id}/ex-post-failures`
  - Auto detection should write `status=candidate, source=auto`; human confirmation appends a `status=confirmed, source=manual` event with the same `case_id`.
- Reporting (monthly/quarterly aggregation):
  - `uv run python scripts/generate_ex_post_failure_report.py --format md --output ex_post_failures.md`
  - GitHub Actions (scheduled/manual): `.github/workflows/ex-post-failure-report.yml` (auto-skips if secrets are missing)
