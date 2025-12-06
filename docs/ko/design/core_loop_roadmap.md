---
title: "Core Loop 중심 아키텍처 로드맵"
tags: [architecture, roadmap, core-loop]
author: "QMTL Team"
last_modified: 2025-12-06
---

# Core Loop 중심 아키텍처 로드맵

## 0. 목적과 범위

이 문서는 `architecture.md`·`gateway.md`·`worldservice.md`·`seamless_data_provider_v2.md` 등에서 정의된 **Core Loop**와 각 컴포넌트의 As‑Is/To‑Be를 종합해, QMTL이 어떤 방향으로 발전해야 하는지 **프로젝트 전반의 로드맵**을 정리한다.

- Core Loop(전략 생애주기)  
  `전략 작성 → 제출 → (월드 안에서 자동 백테스트/평가/배포) → 월드 성과 확인 → 전략 개선`
- 목표: Core Loop에서 정의한 **To‑Be 경험**을 코드/서비스/문서 전반에 일관되게 녹여, 사용자가 “전략 로직에만 집중하면 시스템이 알아서 최적화하고 수익을 내는” 흐름을 실제로 경험하도록 만드는 것.
- 범위: SDK/Runner, WorldService, Gateway/DAG Manager, 데이터 플레인(Seamless), 운영·관측, 품질/테스트/문서를 아우르는 **중장기 구조적 방향**과, 각 영역에서 바로 착수 가능한 **구체적 개선 작업 예시**를 포함한다.

본 문서는 **일정이 박힌 Gantt 차트가 아니라 방향성·우선순위·작업 묶음**을 정의하는 수준을 목표로 한다. 개별 이슈/PR은 이 로드맵의 트랙/마일스톤을 참조해 설계해야 한다.

## 1. North Star: Core Loop 경험

### 1.1 사용자 경험 목표

- 전략 작성자는 “신호 + 필요한 데이터 + 월드 선택”만 정의한다.
- `Runner.submit(..., world=..., mode=...)` 한 번으로:
  - 히스토리 warm‑up + 시장 replay 기반 백테스트,
  - 성과 메트릭 계산 및 정책 평가(WorldService),
  - 전략 활성/비활성 및 월드 단위 자본 배분 계획 생성까지 **연결된 파이프라인**이 실행된다.
- 사용자는 월드/전략의 기여도와 리스크를 하나의 화면/CLI 흐름에서 보고, **“제출 → 관찰 → 개선” 루프**에만 집중한다.

### 1.2 로드맵 상 핵심 제약

- **단순성 > 하위 호환성**  
  레거시 플래그·이중 경로 대신, 명시적인 마이그레이션 가이드를 제공하고 “신 방식”만 남도록 정리한다.
- **WorldService/Graph SSOT 유지**  
  정책·결정·활성·큐/그래프 상태의 단일 진실 소스를 WS/DM에 두고, SDK/Runner·Gateway는 소비자/경계 레이어로 남긴다.
- **Default-Safe**  
  구성/결정이 불충분하거나 모호하면 항상 compute‑only(backtest, 주문 게이트 OFF)로 강등한다.

이 제약을 깨는 변경은 허용되지 않으며, 예외가 필요할 경우 아키텍처 문서에 명시적인 waiver·후속 계획을 기록해야 한다.

### 1.3 프로그램 구조(P‑0/P‑A/B/C)와 트랙 매핑

이 로드맵은 `docs/ko/design/architecture_roadmap_redesign.md`에서 합의한 **수직 프로그램 구조(P‑0/P‑A/B/C)**를 따른다.  
각 작업은 최소 하나 이상의 프로그램과 T1–T6 트랙/마일스톤에 매핑되어야 한다.

- **P‑0 — 플랫폼/공통 인프라/관측 메타‑트랙**  
  Core Loop에 직접 노출되지는 않지만, 모든 프로그램이 공통으로 사용하는 인프라·빌드·관측·운영 개선을 담는다.  
  예: 테스트 인프라, 공통 observability 스택, 비용/성능 개선 등(주로 T5/T6와 연결).
- **P‑A — Core Loop Paved Road v1**  
  신규 전략 작성자가 “Runner.submit + world/preset”만으로 Core Loop를 경험하도록 만드는 **최우선 프로그램**이다.  
  - P‑A P0 핵심 범위:  
    - T1 P0‑M1 (SubmitResult ↔ WS Envelopes 정렬)  
    - T2 P0‑M2 (ExecutionDomain 결정 권한의 WS 단일화, default‑safe 강화)  
    - T6 P0‑M1 (Core Loop 계약 테스트 스켈레톤)  
  - P‑A P1 이후:  
    - T1 P1‑M3 (전략 템플릿/가이드 Core Loop화)  
    - T3 P0‑M1 (world 기반 데이터 preset on‑ramp)  
    - T4 P0‑M1, P0‑M2 (ComputeContext/ExecutionDomain·NodeID/TagQuery 규약 정렬)
- **P‑B — Promotion & Live Safety**  
  전략 승급·라이브 안전성·2‑Phase Apply를 다루는 프로그램으로, P‑A P0 완료 이후 본격화된다.  
  - 주요 매핑:  
    - T2 P0‑M1, P1‑M3 (평가·활성 단일화, 2‑Phase Apply 운용)  
    - T4 P1‑M3 (큐 네임스페이스/ACL 일원화)  
    - T3 P2‑M3 (멀티 업스트림/Tag 기반 자동 큐 매핑)  
    - T5 P0‑M1 (Determinism 체크리스트)
- **P‑C — Data Autopilot & Observability**  
  데이터 플레인 자동화, 스키마 거버넌스, Core Loop 골든 시그널/대시보드를 담당한다.  
  - 주요 매핑:  
    - T3 P0‑M1, P1‑M2 (preset on‑ramp, 스키마 레지스트리 거버넌스)  
    - T5 P1‑M2 (Core Loop 골든 시그널 대시보드)  
    - T6 P2‑M3 (As‑Is/To‑Be 문서 및 로드맵 정합성 유지)

P‑A/B/C/P‑0 중 어느 것에도 매핑되지 않는 변경은 “합리적인 이유가 있는지”부터 검토해야 하며, 필요 시 별도 ADR에서 예외와 후속 계획을 함께 기록한다.

## 2. 로드맵 개요: 트랙과 마일스톤

로드맵은 다음 여섯 개 트랙으로 구성한다. 각 트랙은 Core Loop 상의 위치와 함께, **P0–P2 우선순위 마일스톤**으로 나눈다.

- T1. 전략 경험/SDK 트랙
- T2. 월드/정책(WS) 트랙
- T3. 데이터 플레인/Seamless 트랙
- T4. Gateway/DAG Manager 트랙
- T5. 운영·관측·안전성 트랙
- T6. 품질·테스트·문서화 트랙

각 트랙은 "방향성(Design North Star)" → "핵심 마일스톤(P0–P2)" → "구체적인 작업 예시" 순으로 기술한다.

!!! note "프로그램과의 관계"
    각 트랙의 마일스톤은 상위 프로그램(P-A/B/C)에 매핑된다. PR/이슈 생성 시 "어느 프로그램의 어느 마일스톤을 전진시키는가?"를 명시해야 한다.

## 3. T1 — 전략 경험/SDK 트랙

**연결 프로그램**: P-A (Core Loop Paved Road)

### 3.1 방향성

- **“Runner.submit만 알면 된다”**를 목표로, SDK/Runner의 모든 주요 흐름을 Core Loop에 맞춰 재정렬한다.
- 전략 코드는 **데이터/월드/도메인/큐 관리에서 가능한 한 멀리 떨어진 상태**를 유지하고, 환경 선택·실행 모드·큐 매핑은 런타임·서비스가 담당한다.
- `SubmitResult`/CLI 출력/문서가 **월드 평가·결정·활성 결과**와 자연스럽게 이어지도록 통합한다.

### 3.2 핵심 마일스톤

- **P0‑T1‑M1 — SubmitResult 정규화 및 Core Loop 정렬**
  - Runner.submit/CLI의 반환 타입을 `DecisionEnvelope`/`ActivationEnvelope` 구조와 정렬해, “제출 → 평가 결과 확인” 흐름을 단일 객체/뷰로 제공한다.
  - 실패/경고(예: 데이터 부족, 히스테리시스 미충족)를 일관된 에러/필드로 표준화한다.
- **P0‑T1‑M2 — 실행 모드·도메인 힌트 제거/정규화**
  - SDK가 임의로 `execution_domain`을 선택하거나 강제하는 경로를 제거하고, WorldService 결정 기반의 도메인만 허용한다.
  - `offline`/`sandbox` 등의 모호한 모드는 명시적으로 `backtest`로 정규화하고, 문서에서 폐기한다.
- **P1‑T1‑M3 — 전략 템플릿/가이드 Core Loop화**
  - `guides/strategy_workflow.md`, `guides/sdk_tutorial.md` 등에서 Core Loop를 전제로 한 템플릿/예제만 남기고, “월드 없이 단독 backtest” 중심의 옛 흐름은 보조/부록으로 격하하거나 보관소로 이동한다.
- **P2‑T1‑M4 — 고급 패턴(멀티월드, 섀도우 실행) 통합**
  - Shadow 실행, 멀티월드 전략, TagQuery 기반 멀티자산 팩터 템플릿을 Core Loop 기반으로 재구성한다.

### 3.3 구체적인 작업 예시

- `qmtl/runtime/sdk/submit.py`  
  - `SubmitResult` 구조를 WorldService `DecisionEnvelope`/`ActivationEnvelope`와 동형이 되도록 재정의한다.
  - Core Loop 관점에서 의미 없는 필드(예: 내부용 디버그 플래그)는 SDK 내부로 숨기고, 사용자에게 필요한 필드만 노출한다.
- `docs/ko/guides/strategy_workflow.md`  
  - “전략 코드 → Runner.submit → WorldService 평가 → 활성/비활성 반영” 흐름을 기준으로 전체 예제를 재작성한다.
- `docs/ko/guides/sdk_tutorial.md`  
  - bare Runner 예제보다 월드 기반 예제를 우선 소개하고, `world/world.md`·`world/policy_engine.md`와 교차 링크한다.

## 4. T2 — 월드/정책(WorldService) 트랙

**연결 프로그램**: P-A (평가/활성 단일화), P-B (Promotion & Live Safety)

### 4.1 방향성

- WorldService를 **전략 평가·활성·자본 배분 정책의 단일 진실 소스(SSOT)**로 완성한다.
- SDK/Runner와 Gateway는 WS의 결과를 **변환 없이 그대로 노출하는 thin layer**가 되고, 로컬 평가/ValidationPipeline은 힌트·사전검사 역할로 한정한다.
- ExecutionDomain/2‑Phase Apply/히스테리시스 정책을 문서·코드·운영 가이드에서 동일하게 표현한다.
- Core Loop 단순화 및 정책 프리셋 도입은 **월드/정책 설정의 사용자 측 표면을 평탄화**하는 것을 목표로 하며, WorldService 내부의 게이팅·리스크·관측 정책 표현력을 축소하지 않는다. 프리셋/오버라이드·외부 정책 도구는 모두 `gating_policy` 정규 스키마로 컴파일되는 상위 인터페이스로 취급하고, 필요 시 고급/운영 플로우용 별도 진입점으로 재노출할 수 있어야 한다.

### 4.2 핵심 마일스톤

- **P0‑T2‑M1 — 평가·활성 플로우의 단일화**
  - `ValidationPipeline`과 WorldService 정책 엔진의 역할을 분리하고, “최종 활성/가중치/기여도”는 WS 결과만을 의미하도록 정의한다.
  - Runner.submit/CLI는 WS 결과를 그대로 보여주고, ValidationPipeline 결과는 “사전 검사/추가 지표” 섹션으로 분리한다.
- **P0‑T2‑M2 — ExecutionDomain/effective_mode 규약 정리**
  - `worldservice.md`와 `architecture.md`에서 정의한 ExecutionDomain/effective_mode 규약을 코드에 완전 반영한다.
  - WS API에서 `execution_domain` 생략/모호 입력 시 항상 compute‑only로 강등되도록 검증을 강화한다.
- **P1‑T2‑M3 — 2‑Phase Apply 운용 가이드/도구화**
  - 2‑Phase Apply(Freeze/Drain → Switch → Unfreeze)를 WS/운영 문서와 CLI 도구에서 일관되게 지원한다.
  - Apply 실행/롤백/감사 로그를 WorldAuditLog와 운영 대시보드에서 확인할 수 있도록 한다.
- **P2‑T2‑M4 — 월드 단위 리밸런싱/자본 배분 플로우 완성**
  - `/allocations` API와 Rebalancing 엔진을 Core Loop의 “배포/자본 배분” 단계와 연결하고, 운영 플로우(승인/실행/롤백)를 문서화한다.
  - Runner.submit/CLI에서 제출된 world의 `/allocations` 스냅샷(월드/전략 비중)을 노출해 평가/활성(제안)과 배분(적용) 경계를 명확히 하고, apply/execute는 감사 가능한 운영 단계로 남긴다 (#1817).

### 4.3 구체적인 작업 예시

- `qmtl/services/worldservice/*`  
  - `EvaluateRequest`/`DecisionEnvelope`/`ActivationEnvelope` 구조를 SDK/Runner와 공유되는 스키마 모듈로 끌어올리고, 중복 타입 정의를 제거한다.
  - ExecutionDomain/effective_mode 파이프라인에서 default‑safe 규약을 강제하는 유닛 테스트를 추가한다.
- `docs/ko/architecture/worldservice.md`  
  - As‑Is/To‑Be 섹션에 각 P0 마일스톤의 상태/진행도를 업데이트하고, Runner.submit/CLI와의 연결 예시를 구체화한다.
- Core Loop 계약 테스트  
  - `tests/e2e/core_loop/test_core_loop_stack.py`에 “submit → allocation summary 노출” 경로를 추가해 `/allocations` 스냅샷 노출 계약을 고정한다 (#1817).
- `docs/ko/operations/activation.md`, `docs/ko/operations/rebalancing_execution.md`  
  - 2‑Phase Apply, 활성 TTL/etag, 리밸런싱 승인 플로우를 Core Loop 기준으로 재정리한다.

### 4.4 제출 → 스냅샷 → apply 운영 흐름

- `Runner.submit ... --world <id>`는 제출된 world의 `/allocations` 스냅샷(etag/updated_at 포함)을 **읽기 전용**으로 노출한다. 스냅샷이 누락/만료되면 CLI가 `qmtl world allocations -w <id>`로 새로고침 힌트를 출력한다.
- 운영자가 자본 배분을 적용할 때는 명시적으로 `qmtl world apply <id> --run-id <id> [--plan-file plan.json|--plan '{"activate":[...]}']`를 실행한다. 기본값은 적용하지 않는 안전 모드이며, run_id는 감사/롤백을 위해 항상 요구한다.
- apply/rollback 승인은 운영 단계로 남겨 두고, 모든 배분 변경은 etag/run_id 기반으로 감사 가능해야 한다. 스냅샷 섹션의 가이던스는 submit → allocations 조회 → apply 순서를 그대로 안내해야 한다.

<a id="t3-seamless-track"></a>
## 5. T3 — 데이터 플레인/Seamless 트랙

**연결 프로그램**: P-A (데이터 preset), P-C (Data Autopilot)

### 5.1 방향성

- Core Loop 상 **“데이터 공급 자동화 + 시장 replay 백테스트”** 단계를 Seamless/DataPlane이 책임지도록 구조를 고정한다.
- world/preset + 간단한 데이터 스펙만으로, Runner/CLI가 적절한 Seamless 인스턴스를 자동 구성하고 StreamInput에 주입한다.
- 데이터 품질/백필/SLA/스키마 검증은 **Seamless 내부 파이프라인과 관측 지표**로 보호한다.

### 5.2 핵심 마일스톤

- **P0‑T3‑M1 — world 기반 데이터 preset on‑ramp**
  - `world/world.md`에 world/preset → 데이터 preset 매핑 규약을 정의하고, Runner/CLI가 이를 사용해 Seamless 인스턴스를 자동 구성한다.
  - `history_provider` 직접 구성 패턴은 가능한 한 폐기하거나 보조 경로로 제한한다.
- **P1‑T3‑M2 — 스키마 레지스트리 거버넌스 정식화**
  - Seamless v2 문서의 “카나리/스트릭트 검증” 목표 상태를 구현해, 스키마 변경 시 카나리→스트릭트 전환 플로우를 제공한다.
  - P‑C / T3 P1‑M2 범위는 다음 이슈에 매핑된다.
    - #1150 — 레지스트리 계약/검증 모드/감사: `SchemaRegistryClient`·`RemoteSchemaRegistryClient`, `validation_mode`/`QMTL_SCHEMA_VALIDATION_MODE`, `QMTL_SCHEMA_REGISTRY_URL`, `seamless_schema_validation_failures_total`, `scripts/schema/audit_log.py`.
    - #1151 — 관측·거버넌스 런북: `operations/monitoring/seamless_v2.jsonnet`, `alert_rules.yml`(`SeamlessSla99thDegraded`, `SeamlessBackfillStuckLease`, `SeamlessConformanceFlagSpike`), `scripts/seamless_health_check.py`를 포함해 대시보드/경보/헬스체크가 즉시 사용 가능하다.
    - #1152 — 검증/실패 주입 회귀: Hypothesis 커버리지·실패 주입·관측 스냅샷 테스트(`tests/qmtl/runtime/sdk/test_history_coverage_property.py`, `tests/qmtl/runtime/sdk/test_seamless_provider.py`, `tests/qmtl/foundation/schema/test_registry.py`)를 아래 명령으로 실행하며 CI `test` 잡에서 동일 경로로 실행된다.

      ```
      uv run -m pytest -W error -n auto \
        tests/qmtl/runtime/sdk/test_history_coverage_property.py \
        tests/qmtl/runtime/sdk/test_seamless_provider.py \
        tests/qmtl/foundation/schema/test_registry.py
      ```
- **P2‑T3‑M3 — 멀티 업스트림/Tag 기반 자동 큐 매핑 강화**
  - Tag 기반 멀티 큐·멀티자산 전략에서 데이터 플레인 설정 없이도 적절한 큐를 자동 선택하도록, Gateway/DAG Manager와 Seamless 간의 태그/interval 규약을 강화한다.

### 5.3 구체적인 작업 예시

- `docs/ko/architecture/seamless_data_provider_v2.md`  
  - world preset on‑ramp 규약을 데이터 플레인 관점에서 명시하고, `rewrite_architecture_docs.md`에서 정의한 규약을 통합한다.
- `docs/ko/world/world.md`  
  - world 설정 예시에서 데이터 preset 항목을 추가하고, Runner/CLI가 실제로 어떻게 Seamless 인스턴스를 구성하는지 예제를 포함한다.

## 6. T4 — Gateway/DAG Manager 트랙

**연결 프로그램**: P-A (ComputeContext 정렬), P-B (큐 네임스페이스/ACL)

### 6.1 방향성

- Gateway는 Core Loop에서 “전략 제출 → WS/DM에 대한 단일 진입점 + 결정/큐 이벤트 브리지” 역할만 수행한다.
- DAG Manager는 그래프/노드/큐의 SSOT로서, NodeID/ComputeKey/큐 네임스페이스 규약을 통한 결정성·재사용성을 보장한다.
- ExecutionDomain/ComputeContext 규약은 `architecture.md`에서 정의된 대로 Gateway/DM/SDK 전역에서 동일하게 구현된다.

### 6.2 핵심 마일스톤

- **P0‑T4‑M1 — ComputeContext/ExecutionDomain 규약 정렬**
  - `qmtl/foundation/common/compute_context.py`의 규범을 Gateway `StrategyComputeContext`와 DAG Manager 컨슈머 코드에 완전히 반영한다.
  - 제출 메타의 `execution_domain`/`as_of` 힌트와 WS 결정이 섞이는 As‑Is 경로를 제거하고, WS 결정 우선 규약을 강제한다.
- **P0‑T4‑M2 — NodeID/TagQuery 결정성 보장**
  - TagQueryNode 확장 시 NodeID가 바뀌지 않도록 하는 규약을 DAG Manager/SDK/Gateway에 일관되게 구현하고, 이를 검증하는 테스트/관측 지표를 강화한다.
- **P1‑T4‑M3 — 큐 네임스페이스/ACL 일원화**
  - `{world_id}.{execution_domain}.<topic>` 네임스페이스 규칙을 운영 환경에서 강제하고, 교차 도메인 접근을 ACL로 제어한다.
- **P2‑T4‑M4 — Diff·큐 오케스트레이션 경량화**
  - 고빈도 전략 제출 시 p95 지연을 줄이기 위한 Diff 최적화/큐 생성 정책을 도입한다.

### 6.3 구체적인 작업 예시

- `docs/ko/architecture/gateway.md`, `docs/ko/architecture/dag-manager.md`  
  - S0‑A As‑Is/To‑Be 섹션을 본 로드맵의 T4 마일스톤과 연결해 유지하고, 구현 진행도에 따라 As‑Is를 갱신한다.
- `qmtl/services/gateway/submission/context_service.py`  
  - ComputeContext 구성 로직에서 WS 결정/ExecutionDomain 우선 규약을 강제하고, 위반 시 명시적인 에러/메트릭을 방출한다.

## 7. T5 — 운영·관측·안전성 트랙

**연결 프로그램**: P-B (Determinism), P-C (골든 시그널 대시보드)

### 7.1 방향성

- Core Loop 상 각 단계(제출, 백테스트, 평가, 활성/배포, 자본 배분)에 대해 **관측 가능성과 결정성**을 보장한다.
- commit‑log·ControlBus·Prometheus 지표·대시보드를 통해, 운영자가 “어디에서 무엇이 잘못됐는지”를 빠르게 식별할 수 있게 한다.
- Default‑safe 원칙에 따라, 데이터/결정이 모호할 때는 실패/강등으로 일관되게 동작하도록 한다.

### 7.2 핵심 마일스톤

- **P0‑T5‑M1 — Determinism 체크리스트 마감**
  - `architecture.md`의 Determinism 체크리스트 항목(예: NodeID CRC, NodeCache GC, TagQuery 안정성)을 구현/검증한다.
- **P1‑T5‑M2 — Core Loop 골든 시그널 대시보드 (완료)**
  - Core Loop 단계별 지표(제출 지연, backtest 커버리지, WS 평가 지연, 활성 반영 지연, 자본 배분 실행 상태)를 하나의 대시보드에서 확인할 수 있도록 구성하고, SLO/대시보드를 `operations/core_loop_golden_signals.md`에 고정한다.
- **P2‑T5‑M3 — 실패 플레이북/런북 정비**
  - Neo4j/Kafka/Redis/WorldService 장애 시나리오에 대한 런북을 Core Loop 관점에서 재정리한다.

### 7.3 구체적인 작업 예시

- `docs/ko/operations/monitoring.md`, `docs/ko/operations/seamless_sla_dashboards.md`, `docs/ko/operations/ws_load_testing.md`  
  - Core Loop 단계와 직접 연결되는 지표/대시보드/부하 테스트 플로우를 강조하고, 기존 지표를 Core Loop 기준으로 재분류한다.
- `docs/ko/operations/activation.md`, `docs/ko/operations/rebalancing_execution.md`  
  - 활성/자본 배분 실패 시의 롤백/재시도 전략을 commit‑log 관점에서 문서화한다.

## 8. T6 — 품질·테스트·문서화 트랙

**연결 프로그램**: P-A (Core Loop 계약 테스트), P-C (문서 정리)

### 8.1 방향성

- Core Loop를 지키는 **계약 테스트(Contract Test)**를 우선시하고, 내부 구현 변경에 덜 민감한 테스트 구조를 유지한다.
- radon·mypy·import cycle·docs 링크 체크를 활용해, 아키텍처 문서에서 약속한 설계를 코드가 지속적으로 만족하도록 guardrail을 유지한다.
- 다국어 문서(i18n)는 항상 `docs/ko`를 기준으로 작성/갱신하고, 영어(en)는 한국어 문서의 정확한 번역이 되도록 유지한다.

### 8.2 핵심 마일스톤

- **P0‑T6‑M1 — Core Loop 계약 테스트 스위트**
  - “전략 제출 → 월드 평가/활성 → 안전한 실행/게이팅 → 결과 관찰”을 end‑to‑end로 검증하는 빠른 테스트 스위트를 추가한다.
  - ExecutionDomain default‑safe, WS/Runner SubmitResult 정렬, TagQuery 안정성 등을 포함한다.
- **P1‑T6‑M2 — Radon/복잡도 관리 지속**
  - `docs/ko/maintenance/radon_c_remediation_plan.md`에 따른 C 등급 제거 계획을 Core Loop 민감 코드에 우선 적용한다.
- **P2‑T6‑M3 — 아키텍처 문서 일관성 유지**
  - As‑Is/To‑Be가 여러 문서에 흩어져 있는 부분을 정리하고, 본 로드맵과 상호 참조하도록 유지한다.

### 8.3 구체적인 작업 예시

- `tests/`  
  - Core Loop 계약 테스트를 별도 모듈(예: `tests/e2e/core_loop`)로 구성해, CI에서 빠르게 실행되도록 한다.
- `docs/ko/architecture/architecture.md` 및 관련 아키텍처 문서  
  - As‑Is/To‑Be 섹션이 실제 구현 상태와 어긋나지 않도록 주기적으로 점검하고, 변경 시 본 로드맵 문서와 함께 업데이트한다.

## 9. 이행 현황(2025-12)

- `core_loop_roadmap_tasks.md` / `core_loop_roadmap_tasks2.md`에 정의된 Phase 0–5(이슈 #1755–#1790) 클러스터는 2025-12-06 기준 완료 상태다.
- ExecutionDomain/default-safe 수직 슬라이스(WS 검증/강등, Runner/CLI 힌트 제거, ComputeContext validator)가 반영됐고, `tests/e2e/core_loop` 계약 테스트로 잠금됐다.
- SubmitResult가 WS `DecisionEnvelope`/`ActivationEnvelope` 공용 스키마를 SSOT로 사용하고 `precheck`를 분리하도록 정리됐으며, CLI/SDK JSON 스냅샷과 계약 스위트에서 검증된다.
- world 기반 데이터 preset 온램프(`world.data.presets[]` → Seamless 오토 와이어링, `--data-preset` 옵션)는 core-loop demo world 계약 테스트로 커버된다.
- NodeID/TagQuery 결정성과 Determinism 체크리스트/메트릭/런북이 반영됐으며, 대응은 `../operations/determinism.md`를 따른다.
- Core Loop 골든 시그널 SLO/대시보드가 `../operations/core_loop_golden_signals.md`에 고정되었고, 아키텍처/Seamless 문서의 To‑Be 항목을 반영해 T5 P1‑M2를 달성했다.
- Core Loop 계약 스위트는 `.github/workflows/ci.yml`에서 `CORE_LOOP_STACK_MODE=inproc`으로 CI 게이트로 실행되며, 실패 시 본 로드맵과 `../architecture/architecture.md`에서 의도/대응을 확인한다.

---

## 10. 로드맵 운용 원칙

### 10.1 이슈/PR 관리

- **프로그램 + 트랙/마일스톤 매핑 필수**  
  - 새 기능/리팩터·버그 수정 이슈는 반드시 **P-0/A/B/C 프로그램** 중 하나와, **T1–T6 트랙의 P0–P2 마일스톤** 중 하나 이상에 매핑한다.
  - PR 템플릿에 `Program:`, `Track/Milestone:` 필드를 포함한다.
- **As‑Is/To‑Be 동기화**  
  - 구현이 To‑Be에 가까워질수록, 각 컴포넌트 문서의 As‑Is 부분을 갱신하거나 제거하고, 본 로드맵의 관련 마일스톤 상태를 업데이트한다.
- **복잡도/기술 부채 가시화**  
  - 불가피한 예외/waiver는 해당 코드 근처와 PR 본문에서 "왜 Core Loop 방향성과 다르게 선택했는지"를 설명하고, 본 로드맵에서 후속 계획을 참조한다.

### 10.2 CI Gate

- `tests/e2e/core_loop` 계약 테스트 스위트는 **P-A 완료의 핵심 DOD**이다.
- 이 테스트가 실패하면 관련 모듈 변경은 merge 불가.
- 테스트 스켈레톤은 구현 완료 전에도 "이 테스트가 결국 통과해야 한다"는 목표로 먼저 작성한다.

### 10.3 ADR (Architecture Decision Record)

- 중요한 아키텍처 결정에 한해 ADR을 작성한다.
- ADR에는 "연결된 프로그램(P-0/A/B/C)과 트랙/마일스톤"을 반드시 명시한다.
- 경량화 원칙: 모든 변경에 ADR을 요구하지 않고, **Core Loop 방향성에 영향을 주는 결정**에만 적용한다.

---

## 11. 관련 문서

- [architecture_roadmap_redesign.md](architecture_roadmap_redesign.md) — 이 로드맵의 설계 논의 및 합의 과정 아카이브
- [architecture.md](../architecture/architecture.md) — 전체 아키텍처 개요
- [worldservice.md](../architecture/worldservice.md) — WorldService 상세
- [gateway.md](../architecture/gateway.md) — Gateway 상세
- [seamless_data_provider_v2.md](../architecture/seamless_data_provider_v2.md) — Seamless 데이터 플레인

---

이 로드맵은 Core Loop 관점에서 QMTL의 중장기 방향성을 고정하는 기준 문서로 사용한다. 새로운 기능을 설계할 때는, 먼저 이 문서에서 **어떤 프로그램과 어떤 트랙/마일스톤에 해당하는지**부터 정의한 뒤 설계를 시작해야 한다.
