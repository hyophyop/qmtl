# Data Normalization & Backfill Radon Plan

## Scope

- Focus: end-to-end **data normalization, backfill, and artifact publication** paths spanning live/历史 IO and the Seamless SDK.
- Key modules:
  - `qmtl/runtime/io/ccxt_live_feed.py`
  - `qmtl/runtime/io/artifact.py`
  - `qmtl/runtime/io/historyprovider.py`
  - `qmtl/runtime/io/seamless_provider.py`
  - `qmtl/runtime/io/ccxt_rate_limiter.py`
  - `qmtl/runtime/io/ccxt_fetcher.py`
  - `qmtl/runtime/sdk/seamless_data_provider.py`
- Issues covered by this plan:
  - #1550 (Reduce complexity of data normalization/backfill paths)
  - #1574 (Inventory + design document)
  - #1575 (runtime/io refactor)
  - #1576 (runtime/sdk refactor)

> Canonical content is maintained in `docs/ko/...`; this English page is a translation kept in sync with the Korean original.
Consolidation note (2025-11-24): this document replaces the former Seamless Data Provider Radon Plan and now serves as the single radon tracker for Seamless data normalization/backfill/publication work.

## Current radon snapshot (key C-grade functions)

As of 2025-11-16, running `uv run --with radon -m radon cc -s qmtl/runtime/io qmtl/runtime/sdk/seamless_data_provider.py` yields the following **C-grade blocks directly involved in normalization, backfill, or artifact publication**:

| Path | Symbol | Role | CC grade / score |
| --- | --- | --- | --- |
| `runtime/io/ccxt_live_feed.py:74` | `CcxtProLiveFeed.subscribe` | ccxt.pro live feed subscription, reconnect, mode-specific orchestration | C / 19 |
| `runtime/io/ccxt_live_feed.py:222` | `CcxtProLiveFeed._normalize_records` | OHLCV/trade record normalization and deduplication | C / 16 |
| `runtime/io/ccxt_live_feed.py:283` | `CcxtProLiveFeed._get_or_create_exchange` | ccxt.pro instance creation and market metadata loading | C / 13 |
| `runtime/io/artifact.py:67` | `ArtifactRegistrar.publish` | Publishing normalized frames as artifacts and recording metadata | C / 11 |
| `runtime/io/historyprovider.py:59` | `QuestDBBackend.write_rows` | Writing normalized rows to the QuestDB backend | C / 11 |
| `runtime/io/seamless_provider.py:185` | `DataFetcherAutoBackfiller.backfill` | DataFetcher-based history backfill orchestration | C / 12 |
| `runtime/io/ccxt_rate_limiter.py:177` | `get_limiter` | Building/selecting rate limiters for ccxt calls | C / 16 |
| `runtime/io/ccxt_fetcher.py:258` | `CcxtOHLCVFetcher.fetch` | ccxt OHLCV fetch, retry, and normalization | C / 15 |
| `runtime/sdk/seamless_data_provider.py:1116` | `SeamlessDataProvider._extract_context` | Normalizing compute_context/world/as_of into a request context | C / 17 |
| `runtime/sdk/seamless_data_provider.py:1809` | `SeamlessDataProvider._handle_artifact_publication` | Publication call, fingerprint calculation, metadata normalization | C / 19 |
| `runtime/sdk/seamless_data_provider.py:1297` | `SeamlessDataProvider.fetch` | Top-level orchestration for seamless fetch/backfill/publication | C / 15 |
| `runtime/sdk/seamless_data_provider.py:1990` | `SeamlessDataProvider._resolve_publication_fingerprint` | Normalizing publication fingerprints and selecting modes | C / 16 |
| `runtime/sdk/seamless_data_provider.py:166` | `_load_presets_document` | Loading and normalizing seamless presets documents | C / 16 |
| `runtime/sdk/seamless_data_provider.py:103` | `_read_publish_override_from_config` | Interpreting publish overrides from configuration | C / 12 |
| `runtime/sdk/seamless_data_provider.py:2171` | `SeamlessDataProvider._resolve_downgrade` | Downgrade decisions based on coverage/domain | C / 13 |
| `runtime/sdk/seamless_data_provider.py:2549` | `_RangeOperations._subtract_segment` | Coverage range subtraction for backfill windows | C / 11 |

Although these functions live in separate modules, together they form a single logical pipeline: **data normalization → backfill → artifact publication / coverage computation**.

## Common anti-patterns

Reviewing the C-grade functions reveals recurring issues:

- **Mixed responsibilities**
  - Source/exchange/domain routing, normalization, validation, backfill/publication, and logging/metrics are entangled in the same methods.
  - Examples: `CcxtProLiveFeed.subscribe`, `SeamlessDataProvider.fetch`, `_handle_artifact_publication`.
- **Duplicated normalization/mapping logic**
  - Context fields (timestamp, world, domain, as_of, coverage) are normalized in multiple places with slightly different rules.
  - Example: `_extract_context` combined with `_normalize_world_id`, `_normalize_domain`, `_normalize_as_of`, `_normalize_float`, plus similar logic scattered in IO modules.
- **Fragmented artifact publication/registrar flow**
  - Registrar publish logic is split between IO (`ArtifactRegistrar.publish`) and SDK (`_handle_artifact_publication`), with overlapping responsibilities.
  - Publication fingerprints, coverage_bounds, manifest URIs, and metadata handling rules are distributed across several methods.
- **Complex coverage/backfill range operations**
  - `_RangeOperations._subtract_segment` and `DataFetcherAutoBackfiller.backfill` pack coverage math, backfill range selection, and logging/metrics into single code paths, increasing CC.
- **Hard-to-target test paths**
  - Large methods with many branches push tests toward end-to-end flows rather than focused unit tests for specific branches, which increases regression risk.

## Target design (Strategy, pipeline, and shared helpers)

To reduce complexity in data normalization/backfill paths, we will adopt the following reusable patterns:

- **Source/exchange-specific normalization Strategies**
  - For `CcxtProLiveFeed`, `CcxtOHLCVFetcher`, and the Seamless SDK, introduce source-specific normalization strategies behind a shared interface.
  - Example interfaces:
    - `normalize_ohlcv(raw: Any) -> NormalizedRecord`
    - `normalize_trade(raw: Any) -> NormalizedRecord`
    - `normalize_context(raw: Any) -> _RequestContext`
- **Stepwise pipelines (Pipeline / Builder)**
  - Decompose flows into small, testable steps such as “load → normalize → validate → backfill → publish → metrics/logging”.
  - Each step is implemented as a pure function or a small helper object so unit tests can exercise individual pieces directly.
  - Examples:
    - IO: `fetch_raw` → `normalize_records` → `write_rows` / `publish_artifact`.
    - SDK: `_extract_context` → `fetch_or_backfill` → `_handle_artifact_publication` → `_finalize_metadata_metrics`.
- **Centralized shared helpers**
  - Move world/domain/as_of/min_coverage/max_lag normalization, fingerprint interpretation, coverage_bounds computation, and artifact size/metrics recording into shared helpers.
  - Introduce at least one helper module shared between IO and SDK so C-grade functions remain orchestrators only.
- **Separate error/logging paths**
  - Move exception-handling, retry/backoff, downgrade decisions, and logging/metrics into dedicated helpers or pipeline steps.
  - Keep the “happy path” in each orchestrator short and linear to minimize cyclomatic complexity.

These design rules align with existing architecture notes (for example `architecture/seamless_data_provider_modularity.md`) while focusing specifically on **cross-cutting patterns for normalization/backfill**.

## Sub-issues and execution structure

This plan is executed via the following sub-issues:

- **#1574 — [docs] Data normalization/backfill C-grade function inventory and Strategy/pipeline design**
  - Maintain and refine the C-grade function inventory (table above).
  - Capture Strategy/pipeline/shared-helper design guidelines in this document and its Korean counterpart.
- **#1575 — [runtime/io] Introduce normalization pipeline for `CcxtProLiveFeed.subscribe`**
  - Apply Strategy/pipeline patterns to C-grade functions in the `CcxtProLiveFeed` stack, simplifying normalization, dedupe, and reconnect logic.
- **#1576 — [runtime/sdk] Introduce normalization/backfill/publication pipeline for `SeamlessDataProvider`**
  - Apply pipeline patterns to `_extract_context`, `fetch`, `_handle_artifact_publication`, and `_resolve_publication_fingerprint`, with an emphasis on context normalization, backfill, and publication.

Each sub-issue aims to bring its target C-grade functions down to **B or better** while aligning with the patterns defined in this plan.

## Validation checklist

- radon snapshots
  - `uv run --with radon -m radon cc -s qmtl/runtime/io qmtl/runtime/sdk/seamless_data_provider.py`
  - Optional diff-only check:
    - `git diff --name-only origin/main... | rg '\\.py$' | xargs -r uv run --with radon -m radon cc -s -n C`
- Tests
  - `PYTHONFAULTHANDLER=1 uv run --with pytest-timeout -m pytest -q --timeout=60 --timeout-method=thread --maxfail=1`
  - `uv run -m pytest -W error -n auto`
- Docs build
  - `uv run mkdocs build`

Once PRs satisfying this checklist are merged for the relevant sub-issues, we consider the objective of #1550 (“reduce complexity of data normalization/backfill paths”) achieved.
