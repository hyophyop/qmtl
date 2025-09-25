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
1) Author: propose schema change (PR touching `docs/reference/schemas/*.json` and any relevant code/data adapters).
2) Dry‑run: validate against sample datasets and `SchemaRegistryClient` in a dedicated branch.
3) Approval: obtain double approval (data platform + strategy owner).
4) Rollout: push to the registry with compatibility mode and record audit trail.

Tools
- `qmtl.foundation.schema.SchemaRegistryClient` — in‑memory by default; set `QMTL_SCHEMA_REGISTRY_URL` for remote.
- `scripts/check_design_drift.py` — detects doc/code spec drift.

Guardrails
- Use canary/strict modes during rollout; do not enable strict globally before validating downstream consumers.
- Keep a changelog of `schema_compat_id` and update the Architecture spec when compatibility boundaries change.

{{ nav_links() }}

