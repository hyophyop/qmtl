---
title: "Schema Registry Governance"
tags: [operations]
author: "QMTL Team"
last_modified: 2025-09-25
---

{{ nav_links() }}

# Schema Registry Governance

This runbook defines how schemas and normalization rules are versioned and rolled out in QMTL.

Goals
- Prevent breaking schema changes from reaching production unnoticed.
- Provide a clear approval and dry‑run path for schema updates.

Workflow
1) **Author**: propose schema change (PR touching `docs/reference/schemas/*.json` and any relevant code/data adapters).
2) **Dry‑run**: validate against sample datasets and `SchemaRegistryClient` in a dedicated branch. Run `uv run mkdocs build` to confirm documentation references stay consistent.
3) **Approval**: obtain double approval (data platform + strategy owner) and capture reviewer notes in the PR description.
4) **Canary**: deploy with `validation_mode=canary` for at least 48 hours. Track `seamless_schema_validation_failures_total{subject,mode}` and regression reports. Canary mode allows incompatible schemas to publish but records failures for follow-up.
5) **Strict Rollout**: switch to `validation_mode=strict` only after canary passes. Strict mode blocks incompatible schemas and raises `SchemaValidationError` when breaking fields are removed or mutated. Update the audit log below with the change reference, timestamp, and validation evidence.

Tools
- `qmtl.foundation.schema.SchemaRegistryClient` — in‑memory by default; set `connectors.schema_registry_url` (or the legacy `QMTL_SCHEMA_REGISTRY_URL`) for remote. Configure governance with `validation_mode` or `QMTL_SCHEMA_VALIDATION_MODE` (`canary` default, `strict` for enforcement).
- `scripts/check_design_drift.py` — detects doc/code spec drift.
- `scripts/schema/audit_log.py` — records promotions to strict mode and stores SHA fingerprints of schema bundles.

Validation emits a structured `SchemaValidationReport` and increments the Prometheus counter `seamless_schema_validation_failures_total` when incompatibilities are detected. The counter is labelled by `subject` and `mode` so dashboards can alarm on strict-mode regressions.

Run the audit helper whenever strict rollout completes:

```bash
uv run python scripts/schema/audit_log.py \
  --schema-bundle-sha "<bundle sha>" \
  --change-request "https://qmtl/changes/<id>" \
  --validation-window "48h canary" \
  --notes "no validation failures observed"
```

Pass `--dry-run` to preview the table updates without touching the repository.

Guardrails
- Always stage canary validation before strict mode; never skip the observation window.
- Keep a changelog of `schema_compat_id` and update the Architecture spec when compatibility boundaries change.
- Document every strict-mode promotion in the table below; missing entries will block subsequent schema changes.

## Strict Mode Audit Log

| Date       | Schema Bundle SHA | Change Request | Validation Window | Notes |
|------------|------------------|----------------|-------------------|-------|
| _TBD_      |                  |                |                   |       |

{{ nav_links() }}

