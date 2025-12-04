---
title: "Core Loop 로드맵 P0 이슈 초안"
tags: [architecture, roadmap, issues, core-loop]
author: "QMTL Team"
last_modified: 2025-12-04
---

# Core Loop 로드맵 P0 이슈 초안

`core_loop_roadmap.md`의 P0 마일스톤을 바로 이슈로 만들 수 있도록 에픽 초안을 정리했다. 각 항목은 필요에 따라 구현/문서/테스트 하위 이슈로 쪼개어 진행한다.

## 공통 원칙

- Program + Track/Milestone를 필수로 명시한다(P-0/P-A/B/C, T1–T6 P0–P2).
- Done 정의: 코드·문서·테스트가 함께 갱신되고, 아키텍처 문서 As‑Is/To‑Be 정합성이 유지된 상태.
- Default‑safe, WS SSOT, ExecutionDomain 규약을 어기는 변경은 ADR/waiver로 예외와 후속 계획을 기록한다.

## P0 이슈 초안

### 1. T1 P0‑M1 — SubmitResult 정규화 및 Core Loop 정렬

- Program: P-A (Core Loop Paved Road)
- Track/Milestone: T1 P0-M1
- 목표: Runner.submit/CLI 출력이 `DecisionEnvelope`/`ActivationEnvelope`와 동형이 되도록 정규화해 “제출 → 평가 결과 확인”을 단일 결과로 제공한다.
- 산출물: 새 `SubmitResult`/CLI 출력 포맷, WS 스키마 공유 모듈, 갱신된 가이드(`strategy_workflow.md`, `sdk_tutorial.md`).
- 범위/작업: SDK 내부 필드 정리·비공개화, 실패/경고 표준화, 샘플 출력/문서 업데이트.
- DOD/테스트: Core Loop 계약 테스트에 SubmitResult 스냅샷 추가, WS/SDK 타입 호환 CI 통과.
- 의존성/참조: [core_loop_roadmap.md](core_loop_roadmap.md), [architecture.md](../architecture/architecture.md), [worldservice.md](../architecture/worldservice.md)

### 2. T1 P0‑M2 — 실행 모드·도메인 힌트 제거/정규화

- Program: P-A (Core Loop Paved Road)
- Track/Milestone: T1 P0-M2
- 목표: SDK가 ExecutionDomain을 임의 선택하지 않고, WS 결정 기반으로만 동작하도록 힌트 경로를 제거한다.
- 산출물: `execution_domain`/`mode` 입력 검증 강화, deprecated 모드(backtest 외) 폐기 안내, 문서 정리.
- 범위/작업: Runner/CLI 파라미터 검증, default-safe 강등 로직 명시, 가이드·튜토리얼 수정.
- DOD/테스트: ExecutionDomain 강등/거부 케이스 계약 테스트 추가, CLI/SDK 도움말 업데이트.
- 의존성/참조: [core_loop_roadmap.md](core_loop_roadmap.md), [architecture.md](../architecture/architecture.md)

### 3. T2 P0‑M1 — 평가·활성 플로우 단일화

- Program: P-A (평가/활성 단일화)
- Track/Milestone: T2 P0-M1
- 목표: 최종 활성/가중치/기여도는 WS 결과만을 의미하도록 규약을 고정하고, ValidationPipeline 결과는 사전 검사로 분리한다.
- 산출물: WS 결과 노출 경로(SubmitResult/CLI/API) 정리, ValidationPipeline 출력 분리, 운영/개발자 가이드 업데이트.
- 범위/작업: WS API 스키마 공유, Runner 출력 구성 변경, 문서에 WS SSOT 원칙 명시.
- DOD/테스트: WS 결과와 ValidationPipeline를 혼동하는 경로 제거 검증, 계약 테스트에 활성 결과 노출 검증 추가.
- 의존성/참조: [core_loop_roadmap.md](core_loop_roadmap.md), [worldservice.md](../architecture/worldservice.md)

### 4. T2 P0‑M2 — ExecutionDomain/effective_mode 규약 정리

- Program: P-A (평가/활성 단일화)
- Track/Milestone: T2 P0-M2
- 목표: WS API가 ExecutionDomain 입력 모호 시 compute-only로 강등하도록 검증을 강화하고, 규약을 코드/문서에 일관 반영한다.
- 산출물: WS 입력 검증/에러 메시지, SDK/CLI 강등 메시지, 규약 문서 업데이트.
- 범위/작업: WS 요청 스키마 검증 강화, Runner 제출 힌트 제거, default-safe 경로 테스트 추가.
- DOD/테스트: compute-only 강등 케이스 E2E 테스트, 문서에서 legacy 모드 제거.
- 의존성/참조: [core_loop_roadmap.md](core_loop_roadmap.md), [worldservice.md](../architecture/worldservice.md), [gateway.md](../architecture/gateway.md)

### 5. T3 P0‑M1 — world 기반 데이터 preset on‑ramp

- Program: P-A (데이터 preset), P-C (Data Autopilot)
- Track/Milestone: T3 P0-M1
- 목표: world/preset → 데이터 preset 매핑을 정의하고 Runner/CLI가 Seamless 인스턴스를 자동 구성하도록 한다.
- 산출물: world preset 스펙, Runner/CLI preset 구성 로직, 예제/가이드 갱신.
- 범위/작업: `world/world.md`에 preset 섹션 추가, Seamless 설정 자동화, history_provider 직접 구성 경로 정리.
- DOD/테스트: preset 선택 시 Seamless 주입 E2E 테스트, 문서 예제 실행 검증.
- 의존성/참조: [core_loop_roadmap.md](core_loop_roadmap.md), [seamless_data_provider_v2.md](../architecture/seamless_data_provider_v2.md), [world.md](../world/world.md)

### 6. T4 P0‑M1 — ComputeContext/ExecutionDomain 규약 정렬

- Program: P-A (ComputeContext 정렬)
- Track/Milestone: T4 P0-M1
- 목표: Gateway/DM/SDK가 `compute_context.py` 규범을 동일하게 사용하고 WS 결정 우선 규약을 강제한다.
- 산출물: Gateway/DAG Manager 컨텍스트 구성 리팩터, 제출 메타 검증, 규약 문서 업데이트.
- 범위/작업: WS 결정/ExecutionDomain 우선 로직 적용, as_of/ComputeKey 처리 일원화, 위반 시 명시적 에러/메트릭 추가.
- DOD/테스트: ComputeContext 계약 테스트, WS 결정 무시 경로 차단 확인.
- 의존성/참조: [core_loop_roadmap.md](core_loop_roadmap.md), [gateway.md](../architecture/gateway.md), [dag-manager.md](../architecture/dag-manager.md)

### 7. T4 P0‑M2 — NodeID/TagQuery 결정성 보장

- Program: P-A (ComputeContext 정렬)
- Track/Milestone: T4 P0-M2
- 목표: TagQueryNode 확장 시 NodeID가 안정적으로 유지되도록 결정성 규약을 전 계층에 반영한다.
- 산출물: NodeID 생성 규약/테스트, DAG Manager/Gateway/SDK 공통 검증, 관측 메트릭.
- 범위/작업: NodeID/TagQuery 규약 문서화, 결정성 검증 테스트, 변동 시 알림/로그 추가.
- DOD/테스트: 결정성 회귀 테스트(동일 입력 → 동일 NodeID), 관측 지표 대시보드 연동.
- 의존성/참조: [core_loop_roadmap.md](core_loop_roadmap.md), [dag-manager.md](../architecture/dag-manager.md), [gateway.md](../architecture/gateway.md)

### 8. T5 P0‑M1 — Determinism 체크리스트 마감

- Program: P-B (Determinism)
- Track/Milestone: T5 P0-M1
- 목표: `architecture.md`의 Determinism 체크리스트 항목(NodeID CRC, NodeCache GC, TagQuery 안정성 등)을 구현·검증해 Core Loop 결정성을 확보한다.
- 산출물: 체크리스트 구현/테스트, 운영 체크/메트릭, 런북 업데이트.
- 범위/작업: 결정성 관련 코드 보강, GC/캐시 정책 검증, 관측 지표 추가, 운영 문서 보완.
- DOD/테스트: 결정성 회귀 테스트 통과, 운영 대시보드에서 관련 지표 확인 가능.
- 의존성/참조: [core_loop_roadmap.md](core_loop_roadmap.md), [architecture.md](../architecture/architecture.md), [operations/monitoring.md](../operations/monitoring.md)

### 9. T6 P0‑M1 — Core Loop 계약 테스트 스위트

- Program: P-A (Core Loop 계약 테스트)
- Track/Milestone: T6 P0-M1
- 목표: “전략 제출 → 월드 평가/활성 → 안전한 실행/게이팅 → 결과 관찰”을 빠르게 검증하는 계약 테스트 스위트를 추가한다.
- 산출물: `tests/e2e/core_loop` 스켈레톤, SubmitResult/ExecutionDomain/TagQuery 안정성 케이스, CI 통합.
- 범위/작업: 필수 happy-path/강등 케이스 구현, fixture 단순화, 문서에 테스트 사용법 추가.
- DOD/테스트: CI에서 스위트 기본 통과, 실패 시 merge 불가 규칙 문서화, 관련 아키텍처 문서 교차 링크.
- 의존성/참조: [core_loop_roadmap.md](core_loop_roadmap.md), [architecture.md](../architecture/architecture.md), `tests/e2e/core_loop`
