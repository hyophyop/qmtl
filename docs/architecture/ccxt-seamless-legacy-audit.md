# CCXT × Seamless Legacy Audit

## Summary
This inventory supports the migration tracked in [#1162](https://github.com/hyophyop/qmtl/issues/1162) by cataloging the remaining content inside the legacy CCXT × Seamless design notes. The audit compares each document against the consolidated [`ccxt-seamless-integrated.md`](ccxt-seamless-integrated.md) blueprint and highlights external links that still point at the deprecated files.

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
| **Feature Artifact Plane guardrails** (dataset_fingerprint-as_of discipline preventing domain bleed) | Partially captured | Integrated spec notes fingerprint/as_of usage but does not restate the rationale around read-only artifact sharing across domains. |
| **CCXT worker metadata workflow** (computing dataset_fingerprint/as_of at snapshot time) | Missing | No equivalent description exists for when fingerprints should be produced inside the ingestion workers. |
| **Artifact storage policy** (versioned retention in Feature Artifact store) | Partially captured | Integrated doc names the artifact store but omits the explicit requirement to persist each backfilled segment as an immutable version. |
| **Observability metrics** (`backfill_completion_ratio` alongside SLA counters) | Missing | Current Operational Practices omit this metric carried over from Codex guidance. |
| **Implementation roadmap** (connector packaging, Seamless adapter layer, persistence, domain gating, observability) | Missing | Translate the phased roadmap into the integrated doc’s Implementation Guidance so teams can track migration progress. |

### `ccxt-seamless-hybrid.md`

| Legacy element | Migration status | Notes |
| --- | --- | --- |
| **Comprehensive configuration schema** (retry tuning, metrics catalog, partitioning, fingerprint options) | Partially captured | Integrated YAML includes only a subset of parameters; retry policy, metrics, and artifact partitioning options are still unique to the hybrid doc. |
| **Reference implementation snippets** (`conform_frame`, `compute_fingerprint`, `maybe_publish_artifact`, domain gating helper) | Missing | Integrated doc references `maybe_publish_artifact` conceptually but omits concrete pseudo-code. |
| **Operations & observability checklist** (metric names, alert thresholds, env vars) | Partially captured | Some SLA metrics are listed, but counters like `seamless_storage_wait_ms`, `seamless_backfill_wait_ms`, and alert heuristics remain undocumented. |
| **Storage strategy (Hot vs. Cold) and stabilization workflow** | Missing | No section in the integrated doc calls out QuestDB vs. artifact responsibilities or watermark promotion rules. |
| **Migration pathway & acceptance criteria** | Missing | The actionable seven-step migration plan and validation criteria need a new “Migration Path” section in the integrated blueprint. |

## External Links that Depend on the Legacy Docs
- ✅ `mkdocs.yml` navigation now routes readers directly to the integrated blueprint (the GPT5-High entry was removed).
- ✅ [`ccxt-seamless-integrated.md`](ccxt-seamless-integrated.md) inlines the former GPT5-High material and no longer links out to the archived file.
- [`ccxt-seamless-hybrid.md`](ccxt-seamless-hybrid.md) now references the integrated blueprint for its data-plane lineage; future cleanup can drop the parenthetical entirely once the Codex content is migrated.

## Recommended Follow-Up
1. Incorporate the missing sections listed above into `ccxt-seamless-integrated.md`, preserving diagrams (Mermaid) where appropriate.
2. Update navigation so that the integrated blueprint replaces direct links to the legacy drafts once migration is complete.
3. After porting, archive or delete the redundant documents and post these findings as a comment in [#1162](https://github.com/hyophyop/qmtl/issues/1162) referencing this audit (Fixes #1163).
