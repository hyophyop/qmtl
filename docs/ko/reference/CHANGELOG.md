---
title: "변경 이력"
tags: []
author: "QMTL Team"
last_modified: 2026-01-10
---

<!-- Generated from ../CHANGELOG.md; do not edit manually -->

{{ nav_links() }}

# 변경 이력

## v2.0.0 — QMTL Simplification (2025-11-26)

### ⚡ Breaking Changes

이번 릴리스는 QMTL Simplification Proposal을 적용하여 SDK와 CLI를 대폭 단순화합니다.

**API 변경:**
- **`Runner.run()` → `Runner.submit()`**: 기본 제출 API가 `Runner.submit(strategy, world=, mode=)`로 변경되었습니다. 기존 `Runner.run(world_id=, gateway_url=)`는 제거되었으며 호출 시 안내 오류가 발생합니다.
- **`Runner.offline()` → `Runner.submit(mode="backtest")`**: 오프라인 실행은 통합 submit API에서 처리합니다. 기존 helper는 제거되었습니다.
- **`execution_domain` → `mode`**: 복잡한 4단계 execution domain 매핑을 3가지 모드(`backtest | paper | live`)로 단순화했습니다.

**CLI 변경:**
- **플랫 CLI 구조**: `qmtl submit`, `qmtl status`, `qmtl world`, `qmtl init`가 기존 4단계 계층을 대체합니다.
- **레거시 명령 제거**: `qmtl service sdk`, `qmtl tools sdk`, `qmtl project init`는 더 이상 제공되지 않으며 v2 명령을 사용해야 합니다.
- **운영자 표면 분리**: 서비스 관리 흐름은 공개 author 명령이 아니라 명시적 `qmtl --admin ...` 명령을 사용합니다.
- **설정 단순화**: 복잡한 `gating_policy` YAML 대신 preset 기반 설정(`sandbox | conservative | moderate | aggressive`)을 사용합니다.

### ✨ New Features

**Phase 1: Clean Slate**
- `Runner.submit()` - 기본 world와 gateway를 자동 탐색하는 통합 제출 API
- `StrategySubmitResult` - 상태, 기여도 지표, 피드백을 포함한 종합 결과 객체
- `PolicyPreset` - 4가지 정책 preset(sandbox, conservative, moderate, aggressive)과 간단한 override
- 플랫 구조의 CLI v2

**Phase 2: Automation Pipeline**
- 자동 검증 파이프라인 - 제출된 전략을 자동으로 백테스트하고 평가
- 실시간 기여도 피드백 - 전략 성능 및 포트폴리오 영향 지표를 즉시 제공
- 자동 활성화 - 유효한 전략을 기본 가중치로 자동 활성화

**Phase 3: Internal Cleanup**
- `Mode` enum - 복잡한 execution domain 매핑을 `backtest | paper | live` 모드로 통합
- Mode 유틸리티: `mode_to_execution_domain()`, `execution_domain_to_mode()`, `is_orders_enabled()`, `is_real_time_data()`, `normalize_mode()`
- 레거시 CLI 모듈을 v2로 교체

### 🗑️ Removed

- `Runner.run(world_id=, gateway_url=)` - 제거됨, `Runner.submit(world=)` 사용
- `Runner.offline()` - 제거됨, `Runner.submit(mode="backtest")` 사용
- `qmtl service sdk run` / `qmtl tools sdk` / `qmtl project init` - 제거됨, v2 명령 사용
- 복잡한 `gating_policy` YAML - preset 기반 설정으로 대체

### 📖 Documentation

- 단순화 내용을 `docs/ko/en/architecture/architecture.md` Core Loop 요약으로 이동하고 레거시 디자인 파일 제거
- Phase 1-3 완료 표시
- 마이그레이션 가이드: https://qmtl.readthedocs.io/migrate/v2

### 🧪 Tests

- 687개 테스트 통과, 레거시 테스트 6개 skip
- Mode 유틸리티 테스트 34개 추가
- CLI v2 테스트 18개 추가
- 레거시 CLI 테스트에 skip 마커 추가

---

## Unreleased

- 런타임 지표 스위트에 시간 가중 평균 가격(TWAP) 지표를 추가했습니다.
- 등록된 모든 Node Set 레시피의 체인 길이, descriptor, 모드, portfolio/weight 주입을 검증하는 contract 테스트를 추가했습니다.
- NodeSetRecipe/RecipeAdapterSpec 워크플로우와 신규 테스트를 반영해 Exchange Node Set 아키텍처 및 CCXT 가이드를 업데이트했습니다.
- 호가 미시구조 신호를 위해 로지스틱 오더북 불균형 가중치, 마이크로 프라이스 변환, 관련 문서/예제를 추가했습니다.

- `NodeCache.snapshot()`은 `NodeCache.view()`가 반환하는 읽기 전용 `CacheView`로 대체되었습니다. 전략 코드에서 snapshot helper 호출을 피하십시오.
- 히스토리 프로바이더에 `coverage()`와 `fill_missing()` 인터페이스를 추가하고 `StreamInput`의 `start`/`end` 인자를 제거했습니다.
- `TagQueryNode.resolve()`가 제거되었습니다. 실행 전에 `TagQueryManager.resolve_tags()`로 큐 매핑을 가져오세요.
- 노드 생성 후 태그를 붙일 수 있도록 `Node.add_tag()`를 추가했습니다.
- 레거시 Runner/CLI/Gateway 표면 제거를 위한 마이그레이션 가이드를 추가했습니다. [docs/guides/migration_bc_removal.md](../guides/migration_bc_removal.md)를 참고하세요.
- **Breaking:** 최상위 CLI 별칭(`qmtl dagmanager`, `qmtl gw` 등)을 제거했습니다. 계층형 하위 명령(`qmtl dag manager`, `qmtl gateway` 등)을 사용하세요.
- **Breaking:** 평탄화된 호환성 패키지(`qmtl.brokerage`, `qmtl.sdk`, `qmtl.pipeline` 등)를 제거했습니다. `qmtl.runtime`, `qmtl.foundation`, `qmtl.interfaces`, `qmtl.services`의 계층형 네임스페이스에서 import 하세요.
- NodeID가 `blake3:` 접두사와 함께 BLAKE3를 사용하며 `world_id`를 더 이상 포함하지 않습니다. 레거시 SHA 기반 ID는 일시적으로 지원됩니다. [docs/guides/migration_nodeid_blake3.md](../guides/migration_nodeid_blake3.md)를 참고하세요.
- Live connector에 표준 `BrokerageClient` 및 `LiveDataFeed` SDK 인터페이스와 참고 구현(`HttpBrokerageClient`, `CcxtBrokerageClient`, `WebSocketFeed`), 데모용 `FakeBrokerageClient`를 추가했습니다. [docs/reference/api/connectors.md](../reference/api/connectors.md)와 예시 `qmtl/examples/strategies/dryrun_live_switch_strategy.py`를 참고하세요.

---

## v0.1.0 — Release 0.1 (2026-01-10)

### 주요 내용

- Release 0.1 core loop 흐름(Submit → Evaluate/Activate → Execution/Gating → Observation)을 확정했습니다.
- 헬스/상태 엔드포인트를 갖춘 Gateway 및 DAG Manager 기본 서비스를 제공했습니다.
- 설정 검증과 서비스 기동에 필요한 CLI 표면을 문서화했습니다.
- 0.1 릴리스용 산출물과 문서 빌드 요구사항을 검증했습니다.

---

## v0.1.1-rc1 — Ownership + Commit Log (2025-09-03)

이슈 #544 수용 기준을 위한 하이라이트:

- Ownership handoff metric: OwnershipManager는 다른 워커가 키를 가져갈 때 `owner_reassign_total`을 자동 증가시킵니다(best-effort). StrategyWorker는 ownership 획득 시 `worker_id`를 전달합니다. (PR #596)
- Exactly-once soak tests: (Node×Interval×Bucket) 당 단일 커밋만 유지되고 중복이 없는지 확인하는 다중 라운드 레이스 테스트를 추가했습니다. consumer는 `(node_id, bucket_ts, input_window_hash)`로 중복 제거합니다. (PR #597)
- Commit log consumer CLI: Prometheus 메트릭과 옵션을 제공하는 `qmtl-commitlog-consumer`를 추가했습니다. (PR #598)
- CI hardening: push/PR 트리거를 복구하고 `-W error`, `PYTHONWARNINGS=error`를 강제했습니다. (PR #599)
- Docs: Gateway/DAG Manager 문서에 파티션 키, message-key 포맷, dedup triple, owner handoff metric을 문서화했습니다. (PR #600, #601)

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

{{ nav_links() }}
