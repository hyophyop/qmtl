---
title: "Core Loop 로드맵 P0 이슈 분할안"
tags: [architecture, roadmap, issues, core-loop]
author: "QMTL Team"
last_modified: 2025-12-04
---

# Core Loop 로드맵 P0 이슈 분할안

`core_loop_roadmap_issue_drafts.md`의 9개 P0 에픽을 실제 생성 전에 하위 이슈 수준으로 분할했다.  
아래 1)~3) 항목은 각 에픽 내부의 **작업 단위(Task)**를 나타내며, 실제 GitHub 이슈를 만들 때는 코드·테스트·문서를 한 Story로 묶어 재조직할 수 있다.

ExecutionDomain/ComputeContext, NodeID/TagQuery/Determinism처럼 여러 트랙에 걸치는 주제는 **상위 에픽(ExecutionDomain 정렬, Determinism 체크리스트 등)**에서 묶어 관리하고, 아래 하위 항목의 `Dependencies` 필드로 선행/후행 관계를 명시한다.

## T1 P0-M1 — SubmitResult 정규화

1) 스키마 정렬/공유화  
- 내용: `SubmitResult` ↔ `DecisionEnvelope/ActivationEnvelope` 필드 매핑 정의, WS/SDK 공용 타입 모듈로 통합.  
- 산출물: 스키마 모듈, 호환성 검증 테스트.
 - Dependencies: 없음(동일 에픽 내 다른 작업의 선행 작업). T2 P0-M1 2) 스키마 공유화와 공용 모듈 위치를 공유한다.
 - Out of scope: CLI/SDK 출력 포맷 변경, 가이드/튜토리얼 수정(각각 2), 3)에서 처리).

2) SDK/CLI 출력 정리  
- 내용: 비공개 필드 숨김, 실패/경고 표준 메시지 적용, 샘플 출력 갱신.  
- 산출물: 업데이트된 CLI/SDK 출력, 스냅샷 테스트.
 - Dependencies: T1 P0-M1 1) 스키마 정렬/공유화(공용 타입 정리 이후 적용).  
 - Out of scope: WorldService 내부 스키마/정책 변경(WS 쪽 스키마 구조는 T2 P0-M1, P0-M2에서 다룸).

3) 문서/가이드 업데이트  
- 내용: Core Loop 흐름 기반으로 `strategy_workflow.md`, `sdk_tutorial.md` 갱신.  
- 산출물: 수정된 가이드와 예제 코드.
 - Dependencies: T1 P0-M1 1)·2) 완료 이후 최종 출력/스키마 기준으로 문서화.  
 - Out of scope: 새로운 기능 설계나 추가 API 도입(기존 로드맵 범위 밖의 확장은 포함하지 않음).

참조: [core_loop_roadmap.md](core_loop_roadmap.md), [core_loop_roadmap_issue_drafts.md](core_loop_roadmap_issue_drafts.md)

## T1 P0-M2 — 실행 모드·도메인 정규화

1) 파라미터 검증 강화  
- 내용: `execution_domain/mode` 입력 검증, deprecated 모드 제거.  
- 산출물: 검증 로직, 에러 메시지 정리.
 - Dependencies: 없음(ExecutionDomain 정렬의 입력단 기초 작업). T2 P0-M2 1), T4 P0-M1 1)과 규약 수준에서 정렬 필요.  
 - Out of scope: compute-only 강등 동작 자체(실제 downgrade 경로 구현은 2)에서 다룸), WS API 수준 검증(T2 P0-M2에서 처리).

2) default-safe 강등 로직  
- 내용: 모호/누락 입력 시 compute-only 강등, 로그/메트릭 추가.  
- 산출물: 강등 처리 코드, 회귀 테스트.
 - Dependencies: T1 P0-M2 1) 파라미터 검증 강화(검증 실패/강등 조건 정의 이후 구현). T2 P0-M2 1) WS 입력 검증 강화, T4 P0-M1 1) 규범 반영과 규약 공유.  
 - Out of scope: WS 정책/ExecutionDomain 결정 알고리즘 변경(WS 내부 로직은 T2 P0-M2에서 다룸).

3) 문서/헬프 정리  
- 내용: CLI/SDK 도움말 및 가이드에서 legacy 모드 제거, 규약 명시.  
- 산출물: 갱신된 문서/헬프 텍스트.
 - Dependencies: T1 P0-M2 1)·2) 구현 이후 최종 규약 기준으로 문서화.  
 - Out of scope: WS/API 문서 세부 정책 기술(해당 내용은 worldservice·gateway 문서 이슈에서 다룸).

참조: [core_loop_roadmap.md](core_loop_roadmap.md)

## T2 P0-M1 — 평가·활성 단일화

1) WS SSOT 반영  
- 내용: Runner/CLI/API가 WS 결과만 노출하도록 경로 정리, ValidationPipeline 출력 분리.  
- 산출물: WS 결과 직결 경로, 분리된 사전검사 섹션.
 - Dependencies: T1 P0-M1 1)·2)에서 SubmitResult/출력 구조가 정리되어 있으면 정합성 확보가 쉬움(강한 Block은 아님).  
 - Out of scope: WS 정책 표현식 변경이나 새로운 게이팅 규칙 설계(정책 엔진의 도메인 로직은 로드맵 다른 단계에서 다룸).

2) 스키마 공유화  
- 내용: WS API 스키마를 공용 모듈로 노출, 중복 타입 제거.  
- 산출물: 스키마 모듈, 호환성 테스트.
 - Dependencies: T1 P0-M1 1) 스키마 정렬/공유화와 공용 스키마 모듈 위치를 공유해야 한다.  
 - Out of scope: CLI/SDK 출력 포맷(표현/UX는 T1 P0-M1 2)에서 다룸).

3) 운영/개발 가이드 업데이트  
- 내용: 활성/기여도 해석, ValidationPipeline 위치를 분리해 문서화.  
- 산출물: 갱신된 운영/개발 가이드.
 - Dependencies: T2 P0-M1 1)·2)에서 결과 노출 경로가 정리된 이후 작성.  
 - Out of scope: 세부 런북(장애 시나리오/복구 절차)은 T5 P0-M1 3)에서 확장.

참조: [core_loop_roadmap.md](core_loop_roadmap.md), [worldservice.md](../architecture/worldservice.md)

## T2 P0-M2 — ExecutionDomain 규약 정리

1) WS 입력 검증 강화  
- 내용: 모호/누락 ExecutionDomain 입력 시 compute-only 강등, 에러 메시지 표준화.  
- 산출물: 강화된 검증/메시지, 테스트.
 - Dependencies: T1 P0-M2 1)에서 정의한 입력 검증 규약과 개념을 공유.  
 - Out of scope: Runner/CLI 파라미터 검증/UX(T1 P0-M2에서 다룸).

2) Runner 제출 힌트 제거  
- 내용: 제출 메타에서 도메인 힌트 경로 차단, WS 우선 규약 명시.  
- 산출물: 정리된 제출 경로, 경고/로그.
 - Dependencies: T1 P0-M2 1)·2)에서 Runner/CLI 입력/강등 로직이 정리된 이후 WS 우선 규약 반영.  
 - Out of scope: WS effective_mode 계산 로직 자체(정책/데이터 조건은 변경하지 않음).

3) 테스트/E2E  
- 내용: 강등/거부 케이스 계약 테스트, 문서에서 legacy 모드 삭제.  
- 산출물: 테스트 케이스, 갱신된 문서.
 - Dependencies: T2 P0-M2 1)·2) 구현 이후 E2E 시나리오 작성, T6 P0-M1 1) 스켈레톤과 통합.  
 - Out of scope: Core Loop 범위를 벗어난 비표준 실행 모드(내부 실험용 플래그 등)는 테스트 범위에서 제외.

참조: [core_loop_roadmap.md](core_loop_roadmap.md), [gateway.md](../architecture/gateway.md)

## T3 P0-M1 — world 기반 데이터 preset

1) world preset 스펙  
- 내용: world/preset → 데이터 preset 매핑 규약 정의, 예제 추가.  
- 산출물: `world/world.md` 스펙 섹션.
 - Dependencies: 없음(데이터 preset 도입의 사양 정의 단계).  
 - Out of scope: Seamless 내부 엔진/스토리지 구현 변경(데이터 플레인 내부 최적화는 다른 트랙에서 다룸).

2) Runner/CLI 자동 구성  
- 내용: preset 기반 Seamless 인스턴스 오토와이어링 구현, history_provider 직접 구성 경로 격하.  
- 산출물: 자동 구성 코드, 회귀 테스트.
 - Dependencies: T3 P0-M1 1) world preset 스펙이 확정된 이후 구현. T6 P0-M1 1) 스켈레톤과 연계해 E2E 케이스 추가.  
 - Out of scope: 고급 커스텀 데이터 파이프라인(비표준 history_provider/실험용 플로우는 본 이슈에서 강제하지 않음).

3) 예제/가이드 보강  
- 내용: 실행 가능한 preset 예제, 가이드/튜토리얼 업데이트.  
- 산출물: 갱신된 예제와 문서.
 - Dependencies: T3 P0-M1 1)·2) 구현 이후, 실제 preset 기반 예제가 CI나 계약 테스트에서 동작하는 것을 전제로 문서화.  
 - Out of scope: legacy history_provider-only 경로에 대한 상세 가이드(필요 시 별도 “레거시/실험” 섹션으로 한정).

참조: [core_loop_roadmap.md](core_loop_roadmap.md), [seamless_data_provider_v2.md](../architecture/seamless_data_provider_v2.md), [world.md](../world/world.md)

## T4 P0-M1 — ComputeContext/ExecutionDomain 정렬

1) 규범 반영  
- 내용: `compute_context.py` 규칙을 Gateway/DM/SDK 전역에 적용.  
- 산출물: 컨텍스트 구성 리팩터 코드.
 - Dependencies: `compute_context.py`에 정의된 규범(아키텍처 문서)과 T1 P0-M2 1), T2 P0-M2 1)의 ExecutionDomain 규약.  
 - Out of scope: NodeID/TagQuery 결정성 세부 구현(T4 P0-M2에서 다룸).

2) WS 결정 우선 강제  
- 내용: as_of/ComputeKey 포함 제출 메타 처리 일원화, 우선순위 위반 시 에러/메트릭.  
- 산출물: 검증 로직, 메트릭/로그.
 - Dependencies: T4 P0-M1 1) 규범 반영, T2 P0-M2 1)·2) WS ExecutionDomain 규약 정리 이후 적용.  
 - Out of scope: WS 정책 수준에서의 effective_mode 계산(정책 엔진 로직은 변경하지 않음).

3) 계약 테스트  
- 내용: ComputeContext 결정 경로 테스트 추가.  
- 산출물: 테스트 케이스, CI 통합.
 - Dependencies: T4 P0-M1 1)·2) 구현 이후, T6 P0-M1 1)에서 정의한 테스트 스켈레톤에 케이스 추가.  
 - Out of scope: Core Loop 외의 비표준 ComputeContext(내부 유틸/실험용 경로)는 최소 smoke 수준만 다룸.

참조: [core_loop_roadmap.md](core_loop_roadmap.md), [dag-manager.md](../architecture/dag-manager.md)

## T4 P0-M2 — NodeID/TagQuery 결정성

1) 규약 문서화  
- 내용: NodeID/TagQuery 결정성 규칙 정의 및 공유.  
- 산출물: 문서/주석, 규약 정리.
 - Dependencies: 아키텍처 문서(NodeID/TagQuery 규약 초안)와 기존 구현 리뷰.  
 - Out of scope: Determinism 체크리스트 전반의 모든 항목(다른 항목은 T5 P0-M1에서 다룸).

2) 엔진별 적용  
- 내용: DAG Manager/Gateway/SDK 생성·확장 경로에 결정성 검증 추가.  
- 산출물: 검증 로직, 회귀 테스트.
 - Dependencies: T4 P0-M2 1) 규약 문서화 이후, 엔진별로 순차 적용(DAG Manager → Gateway → SDK 등).  
 - Out of scope: NodeCache GC 정책, cross-context 캐시 히트 등 다른 Determinism 항목(T5 P0-M1로 위임).

3) 관측/테스트  
- 내용: 결정성 회귀 테스트, 변동 시 알림/로그/메트릭 추가.  
- 산출물: 테스트/메트릭, 대시보드 연동.
 - Dependencies: T4 P0-M2 2) 엔진별 적용이 완료된 이후, T5 P0-M1 2) 관측 지표와 연계.  
 - Out of scope: NodeID/TagQuery 외 Determinism 항목(하나의 메트릭에 모든 체크리스트를 억지로 합치지 않는다).

참조: [core_loop_roadmap.md](core_loop_roadmap.md), [dag-manager.md](../architecture/dag-manager.md), [gateway.md](../architecture/gateway.md)

## T5 P0-M1 — Determinism 체크리스트

1) 체크리스트 구현  
- 내용: NodeID CRC, NodeCache GC, TagQuery 안정성 등 코드 반영.  
- 산출물: 구현/보완된 모듈, 단위 테스트.
 - Dependencies: T4 P0-M2 1)·2)에서 NodeID/TagQuery 결정성 규약이 정리/적용된 상태가 이상적이다.  
 - Out of scope: Core Loop와 직접 무관한 비핵심 경로의 Determinism(필요 시 separate issue로 관리).

2) 관측 지표  
- 내용: 결정성 관련 메트릭/로그 추가, 운영 대시보드 연동.  
- 산출물: 메트릭/알림 설정.
 - Dependencies: T5 P0-M1 1) 체크리스트 구현 이후, T4 P0-M2 3)에서 정의한 NodeID/TagQuery 메트릭과 연계.  
 - Out of scope: 모든 시스템 메트릭을 한 대시보드에 모으는 작업(Determinism 관련 핵심 지표에 집중).

3) 런북 보강  
- 내용: 주요 실패/복구 플로우 정리.  
- 산출물: 갱신된 런북.
 - Dependencies: T5 P0-M1 1)·2) 구현 및 대시보드 정비 이후, 실제 운영 시나리오 기준으로 작성.  
 - Out of scope: 일반 장애 대응 가이드(비-Determinism 이슈는 다른 런북/문서에서 다룸).

참조: [core_loop_roadmap.md](core_loop_roadmap.md), [architecture.md](../architecture/architecture.md)

## T6 P0-M1 — Core Loop 계약 테스트 스위트

1) 스켈레톤 구성  
- 내용: `tests/e2e/core_loop` 기본 흐름/fixture 설계.  
- 산출물: 테스트 스켈레톤.
 - Dependencies: 없음(다른 트랙에서 요구하는 계약 테스트 케이스를 수용할 기본 구조 정의).  
 - Out of scope: 개별 기능의 세부 유닛 테스트(각 기능 이슈에서 담당).

2) 핵심 케이스  
- 내용: SubmitResult 정렬, ExecutionDomain default-safe 강등, TagQuery 안정성 케이스 구현.  
- 산출물: 테스트 케이스, 필요 시 xdist-friendly 픽스처.
 - Dependencies: T6 P0-M1 1) 스켈레톤, 및 각 기능 트랙의 최소 구현 상태  
   - T1 P0-M1 SubmitResult 정규화  
   - T1/T2/T4 ExecutionDomain default-safe 정렬  
   - T3 P0-M1 world 기반 preset on-ramp  
   - T4 P0-M2 NodeID/TagQuery 결정성  
 - Out of scope: Core Loop 밖의 보조 플로우(예: 단독 backtest-only 유틸 경로)는 smoke 수준으로만 포함.

3) CI 통합/문서  
- 내용: CI 블로커 규칙 명시, 테스트 사용법 문서화.  
- 산출물: CI 설정/문서.
 - Dependencies: T6 P0-M1 1)·2)에서 스위트 구조와 핵심 케이스가 정착된 이후, CI 파이프라인에 merge-blocking 규칙 추가.  
 - Out of scope: 전체 테스트 파이프라인 재설계(기존 CI 구성은 유지하되 Core Loop 계약 스위트만 게이트로 추가).

참조: [core_loop_roadmap.md](core_loop_roadmap.md), [architecture.md](../architecture/architecture.md), [tests](../../tests)
