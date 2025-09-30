# CCXT × Seamless Legacy Audit

## Summary
This inventory supports the migration tracked in [#1162](https://github.com/hyophyop/qmtl/issues/1162) by cataloging the remaining content inside the legacy CCXT × Seamless design notes. The audit compares each document against the consolidated [`ccxt-seamless-integrated.md`](../architecture/ccxt-seamless-integrated.md) blueprint and highlights external links that still point at the deprecated files. With the legacy drafts now removed from the repository, the tables below remain as a historical record of what was merged where.

## Outstanding Content by Source Document
The following tables list sections, diagrams, or code samples that have no equivalent in the integrated specification. Each row includes migration guidance so that the legacy files can be retired once their content is ported.

### `ccxt-seamless-gpt5high.md`

| Legacy section | Migration status | Notes |
| --- | --- | --- |
| **Data Model** (`ts, open, high, low, close, volume` schema + interval semantics) | ✅ Migrated | Documented under “Data Model & Interval Semantics” in `ccxt-seamless-integrated.md`. |
| **Control Planes → Rate Limiting** (Redis/process split description) | ✅ Migrated | Expanded rate-limiter reference table and environment variable guidance now live in the integrated doc. |
| **Configuration & Recipes** (Python example using `EnhancedQuestDBProvider`) | ✅ Migrated | Example provider wiring added to the Data Plane section of the integrated blueprint. |
| **Operational Guidance** (env vars, metrics, monitoring references) | ✅ Migrated | Operational Practices now enumerate coordinator and Redis env vars plus enriched metrics. |
| **Testing** (mark `slow`, prefer recorded responses) | ✅ Migrated | Implementation and Testing Guidance sections call out pytest preflight, recorded fixtures, and `slow` marks. |
| **Extensions** (future ccxt.pro live feed, synthetic series, trades→bars repair) | ✅ Migrated | Captured in the new “Extensions” section appended to the integrated document. |

### `ccxt-seamless-gpt5codex.md`

| Legacy topic | Migration status | Notes |
| --- | --- | --- |
| **Feature Artifact Plane guardrails** (dataset_fingerprint-as_of discipline preventing domain bleed) | ✅ Migrated | Integrated doc now details read-only sharing, provenance, and the reproducibility contract under "Feature Artifact Plane". |
| **CCXT worker metadata workflow** (computing dataset_fingerprint/as_of at snapshot time) | ✅ Migrated | Publication workflow pseudo-code specifies when workers conform, fingerprint, and publish manifests. |
| **Artifact storage policy** (versioned retention in Feature Artifact store) | ✅ Migrated | Storage policy section clarifies hot vs cold roles, versioning, and watermark promotion. |
| **Observability metrics** (`backfill_completion_ratio` alongside SLA counters) | ✅ Migrated | Operational Practices → Metrics Catalog lists SLA timers, backfill ratios, and gating counters with alert guidance. |
| **Implementation roadmap** (connector packaging, Seamless adapter layer, persistence, domain gating, observability) | ✅ Migrated | Migration Path and Validation Benchmarks outline the phased rollout and acceptance criteria. |

### `ccxt-seamless-hybrid.md`

| Legacy element | Migration status | Notes |
| --- | --- | --- |
| **Comprehensive configuration schema** (retry tuning, metrics catalog, partitioning, fingerprint options) | ✅ Migrated | Configuration blueprint now includes retry knobs, observability thresholds, and artifact partition templates. |
| **Reference implementation snippets** (`conform_frame`, `compute_fingerprint`, `maybe_publish_artifact`, domain gating helper) | ✅ Migrated | Publication workflow pseudo-code replaces the hybrid draft’s snippets. |
| **Operations & observability checklist** (metric names, alert thresholds, env vars) | ✅ Migrated | Operational Practices enumerate metrics, alerts, and environment variables, consolidating the hybrid guidance. |
| **Storage strategy (Hot vs. Cold) and stabilization workflow** | ✅ Migrated | Dedicated storage strategy section documents QuestDB vs artifact responsibilities and promotion sequencing. |
| **Migration pathway & acceptance criteria** | ✅ Migrated | Migration Path and Validation Benchmarks capture the seven-step rollout and readiness checks. |

## External Links that Depend on the Legacy Docs
- ✅ `mkdocs.yml` navigation now routes readers directly to the integrated blueprint (the GPT5-High entry was removed).
- ✅ [`ccxt-seamless-integrated.md`](../architecture/ccxt-seamless-integrated.md) inlines the former GPT5-High material and no longer links out to the archived file.
- Historical `ccxt-seamless-hybrid.md` references have been excised from the tree; consumers should link directly to the integrated blueprint going forward.

## Recommended Follow-Up
1. Confirm the integrated blueprint remains the single source of truth when future updates land; avoid re-introducing split narratives.
2. Keep navigation entries pointing at the integrated document and remove residual references to the archived files across the docset if new links surface.
3. Post migration notes in [#1162](https://github.com/hyophyop/qmtl/issues/1162) summarizing consolidation status for any future follow-on work (Fixes #1163).
