# CCXT × Seamless Legacy Audit

## Summary
This inventory supports the migration tracked in [#1162](https://github.com/hyophyop/qmtl/issues/1162) by cataloging the remaining content inside the legacy CCXT × Seamless design notes. The audit compares each document against the consolidated [`ccxt-seamless-integrated.md`](ccxt-seamless-integrated.md) blueprint and highlights external links that still point at the deprecated files.

## Outstanding Content by Source Document
The following tables list sections, diagrams, or code samples that have no equivalent in the integrated specification. Each row includes migration guidance so that the legacy files can be retired once their content is ported.

### `ccxt-seamless-gpt5high.md`

| Legacy section | Migration status | Notes |
| --- | --- | --- |
| **Data Model** (`ts, open, high, low, close, volume` schema + interval semantics) | Not yet represented | The integrated doc reiterates node ID norms but omits the canonical OHLCV column contract and the interval-normalization rules that gap math expects. |
| **Control Planes → Rate Limiting** (Redis/process split description) | Partially captured | High-level throttling is mentioned, but details such as Redis key partitioning and cluster semantics are only present in the legacy text. |
| **Configuration & Recipes** (Python example using `EnhancedQuestDBProvider`) | Missing | The integrated YAML blueprint lacks a minimal Python snippet; port the sample to aid readers wiring providers in code. |
| **Operational Guidance** (env vars, metrics, monitoring references) | Partially captured | `QMTL_SEAMLESS_COORDINATOR_URL`, `QMTL_CCXT_RATE_LIMITER_REDIS`, and the referenced operations runbooks are absent from the integrated document. |
| **Testing** (mark `slow`, prefer recorded responses) | Missing | Implementation guidance calls for running pytest but does not carry over the advice about slow-test markers or recorded exchange fixtures. |
| **Extensions** (future ccxt.pro live feed, synthetic series, trades→bars repair) | Missing | Capture these roadmap ideas in an "Extensions" or "Future Work" section if they remain relevant. |

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
- `mkdocs.yml` navigation still lists **CCXT × Seamless (GPT5-High)**; readers can reach the deprecated file directly from the sidebar.
- [`ccxt-seamless-integrated.md`](ccxt-seamless-integrated.md) references all three legacy files inside its “Related Documents” list, reinforcing the split-source workflow.
- [`ccxt-seamless-hybrid.md`](ccxt-seamless-hybrid.md) back-links to both GPT5-High and GPT5-Codex documents to describe its lineage.

## Recommended Follow-Up
1. Incorporate the missing sections listed above into `ccxt-seamless-integrated.md`, preserving diagrams (Mermaid) where appropriate.
2. Update navigation so that the integrated blueprint replaces direct links to the legacy drafts once migration is complete.
3. After porting, archive or delete the redundant documents and post these findings as a comment in [#1162](https://github.com/hyophyop/qmtl/issues/1162) referencing this audit (Fixes #1163).
