# World Validation Governance (Override Re-review)

This document operationalizes `world_validation_architecture.md` §12.3 (Invariant 3) by standardizing the **approved override re-review queue, deadlines, and SLA**.

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
