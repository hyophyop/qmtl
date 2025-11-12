---
title: "WorldService/Alpha Radon 개선 계획"
tags: ["radon", "worldservice", "alpha"]
author: "QMTL Team"
last_modified: 2025-11-13
---

{{ nav_links() }}

# WorldService/Alpha Radon 개선 계획

WorldService는 Gateway로부터 들어온 리밸런싱·활성화 요청을 처리하고, MultiWorldRebalanceRequest/Plan 스키마와 `alpha_performance` 지표를 상위 서비스에 노출합니다. 현재 qmtl/services/worldservice/* 모듈에서 복잡도가 높은 경로가 누적되어 있으며(#1513), 새 스키마·메트릭을 게이트 없이 도입할 경우 Gateway/SDK와의 계약이 어긋날 위험이 있습니다. 본 계획은 세계 서비스 핵심 경로의 Radon 등급을 낮추고, Issue #1514 체크리스트를 충족하기 위한 단계별 조치를 정의합니다.

## 진단 요약

| 영역 | 경로 | Radon | 메모 |
| --- | --- | --- | --- |
| Allocation API | `WorldService.upsert_allocations` {{ code_url('qmtl/services/worldservice/services.py#L146') }} | E (32) | 락 획득, 컨텍스트 구축, 플랜 계산, 버스 게시, 실행 호출이 한 함수에 모여 있음 |
| Rebalance Schema | `MultiWorldRebalanceRequest` {{ code_url('qmtl/services/worldservice/schemas.py#L248') }} | 확장 어려움 | 버전 필드/게이트 없음, overlay/nightly 옵션이 동일 모델에 혼재 |
| Decision Metrics | `augment_metrics_with_linearity` {{ code_url('qmtl/services/worldservice/decision.py#L19') }} | C (17) | 새로운 `alpha_performance` 메트릭을 추가하기 어렵고, NaN/누락 처리 규칙이 명확치 않음 |
| Activation Events | `ActivationEventPublisher.upsert_activation` {{ code_url('qmtl/services/worldservice/activation.py#L22') }} | B (8) | freeze/unfreeze, gating 정책, bus publishes가 얽힘 |
| Config Surface | `load_worldservice_server_config` {{ code_url('qmtl/services/worldservice/config.py#L41') }} | C (14) | CLI/서버/테스트에서 다른 옵션을 사용하기 어려움 |

## 목표

- `upsert_allocations` CC를 A/B로 낮추고, Rebalance 계획 계산/저장을 별도 모듈로 분리
- MultiWorldRebalanceRequest/RebalancePlan에 **버전 필드 + Feature Flag**를 추가해 Gateway(#1512)·SDK(#1511)와 동기화
- `alpha_performance` 메트릭 계약(키, 단위, NaN 처리)을 문서화하고, WorldService가 canonical 정의를 보유
- 리밸런싱 경로에 대한 이중 계약 테스트(REST + ControlBus)를 추가하고 `uv run -m pytest -W error -n auto qmtl/services/worldservice/tests` 로 검증

## 개선 트랙

### 1. Allocation 실행 단계화

- `upsert_allocations`를 **락 획득**, **컨텍스트 구성**, **계산 + 저장**, **실행(옵션)** 네 개의 async 함수로 분리. 각 단계는 dataclass(`AllocationExecutionPlan`)를 전달하여 CC를 낮춤.
- Storage, bus, executor 인터페이스를 주입 가능하게 만들어 테스트에서 fake 구현을 사용.
- 결과적으로 `WorldService.upsert_allocations`는 orchestration 역할만 수행(A 등급 목표).

### 2. MultiWorldRebalance 스키마 버저닝

- `MultiWorldRebalanceRequest` / `RebalancePlanModel` / ControlBus 이벤트에 `schema_version: Literal[1,2]` 필드를 추가하고, `mode`, `overlay`, `alpha_metrics` 등 새 필드는 `version>=2`일 때만 필수로 간주.
- 신규 필드: `alpha_metrics`(per-world/per-strategy `alpha_performance` 사전), `rebalance_intent` 메타(추후 overlay/hybrid 지원 대비).
- 게이트 플래그: `WorldServiceConfig.compat_rebalance_v2` 및 ControlBus 토픽 메타에 동일 값을 노출. Gateway health(#1512)와 Issue #1514 체크리스트 항목(WS Schema Note)를 동시 충족.
- 배포 파라미터: `worldservice.server.compat_rebalance_v2`로 v2 지원을 켜고, `worldservice.server.alpha_metrics_required`로 schema_version<2 요청을 거부하도록 `create_app()` 전체 경로에 연결한다.

### 3. Alpha 메트릭 파이프라인 정비

- `decision.augment_metrics_with_linearity`를 리팩터링하여 `alpha_performance` 계산기를 주입하고, NaN/누락 처리 규칙(`0.0` 기본, `alpha_performance.<metric>` 네임스페이스)을 명문화.
- WorldService는 canonical metric spec을 docs/ko/world/rebalancing.md 및 본 문서에 기록하고, SDK/Report CLI는 이를 참조.
- ControlBus 리밸런싱 이벤트에 `alpha_metrics`가 존재하면 그대로 전달, 없으면 빈 dict를 기록.

### 4. Activation/Config 모듈화

- `ActivationEventPublisher`를 command object로 분해하여 freeze/unfreeze/upsert가 별도 메서드 체계로 분기.
- `load_worldservice_server_config`는 BaseSettings 스타일 팩토리를 사용해 CLI/pytest에서 같은 로직을 공유; 신규 게이트(`compat_rebalance_v2`, `alpha_metrics_required`)를 여기서 활성화.

### 5. 테스트 및 문서

- REST `/rebalancing/plan|apply`·ControlBus publish 경로에 대해 버전별 contract 테스트를 추가. (v1 JSON snapshot, v2 JSON snapshot)
- `uv run -m pytest -W error -n auto qmtl/services/worldservice/tests` + preflight timeout 테스트.
- `docs/ko/architecture/worldservice.md`, `docs/ko/world/rebalancing.md`, `docs/ko/guides/strategy_workflow.md`에 버전/메트릭 binding을 업데이트.

## 일정

| 단계 | 기간 | 산출물 |
| --- | --- | --- |
| Phase 1 | 2일 | Allocation 단계화, 테스트 더블 주입 포인트 |
| Phase 2 | 3일 | v2 스키마 정의, Feature Flag, ControlBus/REST 계약 테스트 |
| Phase 3 | 2일 | Alpha 메트릭 문서/코드 정리, Activation/Config 리팩터링 |

## 의존성

- Gateway(#1512)는 v2 게이트 플래그를 health 및 `/rebalancing/execute`에 노출해야 하며, SDK(#1511)는 새 메트릭 키를 소비할 parser를 제공해야 Issue #1514를 닫을 수 있습니다.
- CI에서 `uv run mkdocs build` 를 실행하여 ko/en 동기화를 검증합니다.
