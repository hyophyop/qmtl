# Changelog

## v2.0.0 — QMTL Simplification (2025-11-26)

### ⚡ Breaking Changes

This release implements the QMTL Simplification Proposal, fundamentally restructuring the SDK and CLI for a dramatically simpler user experience.

**API Changes:**
- **`Runner.run()` → `Runner.submit()`**: The primary strategy submission API is now `Runner.submit(strategy, world=, mode=)`. Legacy `Runner.run(world_id=, gateway_url=)` has been removed; calls now raise with guidance.
- **`Runner.offline()` → `Runner.submit(mode="backtest")`**: Offline execution is now handled via the unified submit API; the legacy helpers are removed.
- **`execution_domain` → `mode`**: The complex 4-level execution domain mapping is now exposed as a simple 3-mode interface (`backtest | paper | live`).

**CLI Changes:**
- **Flat CLI structure**: `qmtl submit`, `qmtl status`, `qmtl world`, `qmtl init` replace the old 4-level hierarchy.
- **Legacy commands removed**: `qmtl service sdk`, `qmtl tools sdk`, `qmtl project init` are no longer available; use v2 commands exclusively.
- **Simplified configuration**: Complex gating_policy YAML replaced with preset-based config (`sandbox | conservative | moderate | aggressive`).

### ✨ New Features

**Phase 1: Clean Slate**
- `Runner.submit()` - unified strategy submission with auto-discovery of default world and gateway
- `StrategySubmitResult` - comprehensive result object with status, contribution metrics, and feedback
- `PolicyPreset` - 4 preset policies (sandbox, conservative, moderate, aggressive) with simple overrides
- CLI v2 with flat command structure

**Phase 2: Automation Pipeline**
- Automatic validation pipeline - strategies are automatically backtested and evaluated on submission
- Real-time contribution feedback - immediate metrics on strategy performance and portfolio impact
- Auto-activation - valid strategies are automatically activated with default weights

**Phase 3: Internal Cleanup**
- `Mode` enum - unified `backtest | paper | live` modes replacing complex execution domain mapping
- Mode utilities: `mode_to_execution_domain()`, `execution_domain_to_mode()`, `is_orders_enabled()`, `is_real_time_data()`, `normalize_mode()`
- Legacy CLI modules removed in favor of v2

### 🗑️ Removed

- `Runner.run(world_id=, gateway_url=)` - removed; use `Runner.submit(world=)`
- `Runner.offline()` - removed; use `Runner.submit(mode="backtest")`
- `qmtl service sdk run` / `qmtl tools sdk` / `qmtl project init` - removed; use v2 commands
- Complex `gating_policy` YAML - use preset-based configuration instead

### 📖 Documentation

- Moved simplification content into `docs/ko/en/architecture/architecture.md` Core Loop summary and removed legacy design file
- All phases (1-3) marked as completed
- Migration guide available at https://qmtl.readthedocs.io/migrate/v2

### 🧪 Tests

- 687 tests passing, 6 legacy tests skipped
- 34 new mode utility tests
- 18 new CLI v2 tests
- Updated legacy CLI tests with skip markers

---

## Unreleased

- Added a time-weighted average price (TWAP) indicator to the runtime
  indicator suite.
- Added contract tests covering all registered Node Set recipes to verify chain length, descriptors, modes, and portfolio/weight injection.
- Updated exchange Node Set architecture and CCXT guides to document the NodeSetRecipe/RecipeAdapterSpec workflow and reference the new tests.
- Added logistic order-book imbalance weights, micro-price transforms, and supporting documentation/examples for microstructure signals.

- `NodeCache.snapshot()` has been deprecated in favor of the read-only `CacheView` returned by `NodeCache.view()`. Strategy code should avoid calling the snapshot helper.
- Added `coverage()` and `fill_missing()` interfaces for history providers and removed `start`/`end` arguments from `StreamInput`.
- `TagQueryNode.resolve()` has been removed. Use `TagQueryManager.resolve_tags()` to fetch queue mappings before execution.
- Added `Node.add_tag()` to attach tags after node creation.
- Added migration guide for removing legacy Runner/CLI/Gateway surfaces. See [docs/guides/migration_bc_removal.md](docs/guides/migration_bc_removal.md).
- **Breaking:** Removed the deprecated top-level CLI aliases (`qmtl dagmanager`, `qmtl gw`, etc.); use the hierarchical subcommands (`qmtl dag manager`, `qmtl gateway`, and related) instead.
- **Breaking:** Removed the flattened compatibility packages (`qmtl.brokerage`, `qmtl.sdk`, `qmtl.pipeline`, etc.). Import from the layered namespaces under `qmtl.runtime`, `qmtl.foundation`, `qmtl.interfaces`, or `qmtl.services` instead.
- NodeID now uses BLAKE3 with a `blake3:` prefix and no longer includes `world_id`. Legacy SHA-based IDs remain temporarily supported. See [docs/guides/migration_nodeid_blake3.md](docs/guides/migration_nodeid_blake3.md).
- Live connectors: added standard `BrokerageClient` and `LiveDataFeed` SDK interfaces with reference implementations (`HttpBrokerageClient`, `CcxtBrokerageClient`, `WebSocketFeed`) and a `FakeBrokerageClient` for demos. See [docs/reference/api/connectors.md](docs/reference/api/connectors.md) and example `qmtl/examples/strategies/dryrun_live_switch_strategy.py`.

---

## v0.1.1-rc1 — Ownership + Commit Log (2025-09-03)

Highlights for issue #544 acceptance:

- Ownership handoff metric: OwnershipManager now auto-increments `owner_reassign_total` when a different worker takes over a key (best-effort). StrategyWorker passes its `worker_id` to ownership acquisition. (PR #596)
- Exactly-once soak tests: Added multi-round race test to ensure a single commit per (Node×Interval×Bucket) with zero duplicates; consumer deduplicates by `(node_id, bucket_ts, input_window_hash)`. (PR #597)
- Commit log consumer CLI: Added `qmtl-commitlog-consumer` with Prometheus metrics and configurable options. (PR #598)
- CI hardening: Re-enabled push/PR triggers; enforce `-W error` and `PYTHONWARNINGS=error`. (PR #599)
- Docs: Documented partition key, message-key format, dedup triple, and owner handoff metric in Gateway and DAG Manager docs. (PR #600, #601)

Contributors: @hyophyop


### Infra: CI 임시 비활성화 및 문서 안내 (2025-08-14)

PR 제목: ci: temporarily disable GitHub Actions auto triggers; update docs for manual verification (2025-08-14)

PR 본문:
```
## 변경 내용
- `.github/workflows/ci.yml`, `qmtl/.github/workflows/ci.yml`에서 push/pull_request 트리거 제거, workflow_dispatch만 남김 (CI 임시 비활성화)
- `CONTRIBUTING.md`에 CI 비활성화 공지 및 로컬 검증 절차 추가

## 참고
- CI는 수동으로만 실행 가능하며, PR/커밋 시 자동 검증이 동작하지 않습니다.
- 로컬에서 lint/테스트/문서 동기화 체크 후 PR 생성 바랍니다.
- CI 복구 시 본문/문서에서 안내 예정
```
