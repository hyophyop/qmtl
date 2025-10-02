# Changelog

## Unreleased

- Added contract tests covering all registered Node Set recipes to verify chain length, descriptors, modes, and portfolio/weight injection.
- Updated exchange Node Set architecture and CCXT guides to document the NodeSetRecipe/RecipeAdapterSpec workflow and reference the new tests.

- `NodeCache.snapshot()` has been deprecated in favor of the read-only `CacheView` returned by `NodeCache.view()`. Strategy code should avoid calling the snapshot helper.
- Added `coverage()` and `fill_missing()` interfaces for history providers and removed `start`/`end` arguments from `StreamInput`.
- `TagQueryNode.resolve()` has been removed. Use `TagQueryManager.resolve_tags()` to fetch queue mappings before execution.
- Added `Node.add_tag()` to attach tags after node creation.
- Added migration guide for removing legacy Runner/CLI/Gateway surfaces. See [docs/guides/migration_bc_removal.md](docs/guides/migration_bc_removal.md).
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
