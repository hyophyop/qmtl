---
title: "SDK 런타임 Radon 개선 계획"
tags: ["radon", "sdk", "runtime"]
author: "QMTL Team"
last_modified: 2025-11-13
---

{{ nav_links() }}

# SDK 런타임 Radon 개선 계획

SDK·런타임 계층은 Gateway/DAG에서 정해진 계약을 실행 환경과 WorldService API로 전달하는 중간 물리 계층입니다. 2025‑11 스캔 결과, `qmtl/runtime`과 `qmtl/runtime/sdk`에서 30개 이상의 C/D/E 구간이 확인되었으며 특히 SeamlessDataProvider, 히스토리 워밍업, `alpha_performance` 변환이 복잡도 상승을 주도했습니다. 본 계획은 런타임 계층의 복잡도를 낮추고 `alpha_performance` 메트릭 계약을 SDK↔WorldService↔Gateway 전체에서 일관되게 다루기 위한 블루프린트입니다.

## 진단 요약

| 영역 | 경로 | Radon | 메모 |
| --- | --- | --- | --- |
| Execution Context | `resolve_execution_context` {{ code_url('qmtl/runtime/sdk/execution_context.py#L93') }} | E (31) | Backtest/Live/Shadow 분기를 한 함수에서 처리 |
| Seamless Provider | `SeamlessDataProvider.ensure_data_available` {{ code_url('qmtl/runtime/sdk/seamless_data_provider.py#L1486') }} | E (31) | 데이터 도메인 게이트, 아티팩트 다운로드, 다운그레이드 처리를 한 곳에 결합 |
| Seamless Provider | `_domain_gate` {{ code_url('qmtl/runtime/sdk/seamless_data_provider.py#L1176') }}, `_fetch_seamless` {{ code_url('qmtl/runtime/sdk/seamless_data_provider.py#L1630') }}, `_subtract_ranges` {{ code_url('qmtl/runtime/sdk/seamless_data_provider.py#L2692') }} | D (23‑24) | config/네트워크/산술 계산이 혼재 |
| History Warmup | `HistoryWarmupService.warmup_strategy` {{ code_url('qmtl/runtime/sdk/history_warmup_service.py#L356') }} | D (22) | 백필·재생·검증 로직이 단일 루프로 묶임 |
| Activation Feed | `ActivationManager._on_message` {{ code_url('qmtl/runtime/sdk/activation_manager.py#L111') }} | D (24) | WS 메시지 파싱, 파라미터 검증, 캐시 업데이트가 한 함수 |
| Alpha Metrics | `alpha_performance_node` {{ code_url('qmtl/runtime/transforms/alpha_performance.py#L49') }} | D (21) | 지표 계산, 실행 비용 조정, 결과 포맷이 결합되어 신형 키(`alpha_performance`) 반영이 어려움 |
| Dispatch | `TradeOrderDispatcher.dispatch` {{ code_url('qmtl/runtime/sdk/trade_dispatcher.py#L72') }} | C (20) | 라우팅/재시도/메트릭이 뒤엉켜 Gateway 오류 분류가 어렵다 |

## 목표

- 상기 D/E 구간을 **B 등급 이하로 축소**, `alpha_performance` 변환은 A 등급을 목표
- `alpha_performance` 메트릭 키/단위를 SDK, Gateway, WorldService 문서에 정리하고 파서를 **기본적으로 널 안전**하게 유지
- SeamlessDataProvider/HistoryWarmup 경로에 **단위 테스트 가능한 빌더 패턴** 도입, 네트워크 부작용 최소화
- CI에서 `uv run --with radon -m radon cc -s -n C qmtl/runtime qmtl/runtime/sdk` 를 고정 실행

## 개선 트랙

### 1. 실행 컨텍스트/Dispatch 정규화

- `resolve_execution_context`를 **모드별 전략 객체**(backtest/live/shadow/replay)로 분리하고, Gateway health에서 받은 `compute_context`·`rebalance_schema_version`·`alpha_performance` capability 비트를 그대로 전달.
- `TradeOrderDispatcher.dispatch`는 라우팅/재시도/메트릭 3단계 파이프라인으로 나눠 CC<10 달성. 각 단계는 dataclass 기반 입력(`DispatchEnvelope`)을 사용해 테스트 용이성 확보.

### 2. SeamlessDataProvider 모듈화

- `ensure_data_available` 안의 영역을 ① 도메인 게이트(`_domain_gate`), ② 아티팩트 판별·다운로드, ③ 구간 산술/병합, ④ 다운그레이드 처리 단계로 쪼개어 각각 독립 함수/클래스로 이전.
- `_fetch_seamless`, `_subtract_ranges`는 **순수 함수**로 두고 I/O는 콜백 주입. 이를 통해 unit test에서 메모리 상 맵만으로 검증 가능.
- `_handle_artifact_publication`, `_resolve_publication_fingerprint` 등 부수 작업은 이벤트 버스 클래스로 이동해 메인 클래스의 CC를 줄입니다.

### 3. 히스토리 워밍업 파이프라인화

- `HistoryWarmupService.warmup_strategy`를 **플로우 그래프**로 재작성: (요청 결정 → 히스토리 확보 → Gap 분석 → Replay → 검증). 각 단계가 Generator/async 함수로 나뉘어 CC를 줄이고, `ensure_strict_history`와 재사용.
- `_ensure_node_with_plan`, `replay_events_simple`를 테스트 지원 모듈로 옮겨 `pytest`에서 빠르게 검증.

### 4. Activation/WS 수신기 보호

- `ActivationManager._on_message`는 메시지 구문 분석을 Pydantic 모델로 위임하고, **존재하지 않는 키 무시 + 새 키 feature flag** 전략을 도입해 Issue #1514 체크리스트 중 SDK 항목을 만족.
- Weight 계산(`weight_for_side`)을 별도 pure 함수로 분리해 `alpha_performance` 등 추가 메트릭을 safely 기록.

### 5. Alpha Performance 재구성

- `alpha_performance_node`를 지표별 계산기 클래스로 분할하고, 실행 비용 조정·메트릭 포맷터를 별도 함수로 옮겨 CC<10 목표.
- 결과 Dict에 `alpha_performance.{metric}` 네임스페이스를 적용하고, WorldService 문서(#1513)와 동일 키/단위를 명시.
- SDK 측 Parser는 존재하지 않는 키를 무시하고, 새 키는 Feature Flag를 통해 opt-in 하도록 설계(이슈 #1514 3번째 항목).

### 6. 문서·테스트

- 본 계획을 `docs/ko/guides/sdk_tutorial.md`, `docs/ko/reference/report_cli.md`에 링크해 `alpha_performance` 변경 사항을 추적.
- 테스트: `uv run -m pytest -W error -n auto qmtl/runtime/sdk/tests qmtl/runtime/tests` + preflight `PYTHONFAULTHANDLER=1 uv run --with pytest-timeout -m pytest -q --timeout=60 --timeout-method=thread --maxfail=1`.
- Radon 회귀: `uv run --with radon -m radon cc -s -n C qmtl/runtime qmtl/runtime/sdk`.

## 일정

| 단계 | 기간 | 산출물 |
| --- | --- | --- |
| Phase 1 | 3일 | ExecutionContext/Dispatcher 모듈, `alpha_performance` 계산기 초안, parser fallback |
| Phase 2 | 4일 | SeamlessDataProvider 단계화, 히스토리 워밍업 파이프라인, 단위 테스트 |
| Phase 3 | 2일 | Activation/WS parser 업데이트, 문서·Radon 스냅샷, `uv run mkdocs build` 결과 |

## 상호 의존성

- Gateway/DAG 계획(#1512)에서 제공하는 compatibility flag와 health 비트를 SDK에서 소비해야 하므로 Phase 1 deliverable에 포함.
- WorldService 계획(#1513)에서 확정될 `MultiWorldRebalanceRequest` v2, `alpha_performance` 문서 규격을 SDK 문서에도 동기화.
- Issue #1514 체크리스트 중 SDK Parser Update 항목은 본 계획의 Phase 3 완료 조건입니다.
