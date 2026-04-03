---
title: "QMTL 문서 체계와 계층 분리"
tags:
  - architecture
  - documentation
  - design
author: "QMTL 팀"
last_modified: 2026-04-03
---

{{ nav_links() }}

# QMTL 문서 체계와 계층 분리

## 관련 문서

- [아키텍처 개요](README.md)
- [QMTL 설계 원칙](design_principles.md)
- [QMTL 구현 추적성](implementation_traceability.md)
- [Docs Internationalization](../guides/docs_internationalization.md)
- [Backend Quickstart](../operations/backend_quickstart.md)

## 목적

QMTL 문서는 다음 네 종류의 질문에 동시에 답하려고 하면서 점차 커졌다.

- 이 시스템이 지켜야 하는 설계 규범은 무엇인가?
- 사용자는 어떤 표면 계약만 알면 되는가?
- 운영자는 어떤 절차와 승인 플로우를 따라야 하는가?
- 현재 구현은 어디까지 와 있는가?

이 네 질문은 중요하지만 목적이 다르다. 한 문서 안에 함께 섞이면,
독자는 다음을 구분하기 어려워진다.

- 영속 규범과 현재 구현 세부
- 사용자용 단순 계약과 운영자용 고급 절차
- 제품 표면과 내부 서비스 구조
- 현재 상태 설명과 미래 상태 설계

이 문서는 QMTL 문서를 목적별 계층으로 분리하기 위한 정보 구조를 정의한다.

## 문제 진단

현재 문서 체계의 주된 문제는 “문서가 많다”가 아니라 “문서 목적이 섞여 있다”는 점이다.

- 규범 아키텍처 문서 안에 현재 구현 상태, deprecated 경고, 운영 quickstart가 같이 들어간다.
- Core Loop의 단순 사용자 계약과 승인/감사/리밸런싱 같은 운영 계약이 한 흐름으로 서술된다.
- 설계 원칙 문서와 구현 추적 문서가 가까이 있지만, 독자가 둘의 차이를 먼저 배우지는 못한다.
- 운영 규칙이 설계 규범처럼 읽히거나, 반대로 설계 규범이 임시 운영 방침처럼 읽힌다.

## 설계 목표

- **규범은 짧고 단단하게 유지한다.**
- **사용자 golden path를 운영 절차와 분리한다.**
- **현재 구현 상태는 설계 계약과 별도 계층에 둔다.**
- **문서 링크만 봐도 “무슨 질문에 답하는 문서인지” 알 수 있게 한다.**

## 비목표

- 모든 문서를 즉시 재작성하는 것
- 설계와 운영을 완전히 분리해 상호 링크를 없애는 것
- 한 문서에 하나의 사실만 남기도록 과도하게 파편화하는 것

## 문서 계층

### 1. Principles

질문: “QMTL이 어떤 종류의 설계 판단을 좋은 것으로 보는가?”

- 내용:
  - 변하지 않는 설계 원칙
  - capability-first, semantic boundary, default-safe 같은 판단 기준
  - 새 기능을 어디에 배치해야 하는지에 대한 규범
- 포함:
  - [QMTL 설계 원칙](design_principles.md)
  - [QMTL Capability Map](capability_map.md)
  - [QMTL Semantic Types](semantic_types.md)
  - [QMTL Decision Algebra](decision_algebra.md)
- 제외:
  - 현재 API 경로 목록
  - 현재 구현 상태
  - 운영 절차

### 2. Normative Architecture

질문: “시스템 경계와 SSOT, 프로토콜 계약은 무엇인가?”

- 내용:
  - 서비스 책임과 SSOT 경계
  - 상태 전이와 envelope/contract
  - data plane/control plane/execution plane의 정식 인터페이스
- 포함:
  - [Gateway](gateway.md)
  - [DAG Manager](dag-manager.md)
  - [WorldService](worldservice.md)
  - [ControlBus](controlbus.md)
  - [Risk Signal Hub](risk_signal_hub.md)
  - [실행 상태 머신과 TIF 정책](execution_state.md)
- 제외:
  - 배포 절차
  - 현재 partial/planned 여부
  - 사용자 onboarding용 설명

### 3. Product Contracts

질문: “사용자나 상위 클라이언트는 무엇만 알면 되는가?”

- 내용:
  - `Runner.submit(..., world=...)` 같은 golden path
  - 사용자가 직접 보는 결과 계약
  - 간단한 phase model, 승인 지점, 읽기 전용 관측 표면
- 포함 예시:
  - Core Loop 문서
  - world campaign loop의 사용자 계약
  - allocation/apply의 제품 수준 흐름
- 제외:
  - 내부 구현 클래스
  - 운영 세부 파라미터
  - 실험적 스키마 협상 토글

### 4. Operations

질문: “운영자는 무엇을 어떻게 실행하고 감시하고 승인하는가?”

- 내용:
  - 배포, 모니터링, 승인, 장애 대응, 롤아웃, 감사
  - CLI runbook, observability, SLO, incident 대응
- 포함:
  - `docs/operations/` 전반
  - 승인 플로우, activation/rebalancing runbook
- 제외:
  - 코어 의미론 정의
  - 사용자용 제품 약속

### 5. Implementation Status

질문: “현재 구현은 어디까지 왔고, 어떤 부분이 partial/planned인가?”

- 내용:
  - 추적성 매핑
  - planned/partial/implemented 상태
  - 대표 코드/테스트 근거
- 포함:
  - [QMTL 구현 추적성](implementation_traceability.md)
- 제외:
  - 규범적 주장을 새로 만드는 서술
  - 운영 절차

### 6. Migration & Deprecation

질문: “이전 방식에서 새 방식으로 어떻게 이동하는가?”

- 내용:
  - deprecated 경고
  - breaking change 가이드
  - moved 문서, 이전 경로에서 새 경로로의 연결
- 포함:
  - `guides/migration_*`
  - moved marker 문서
- 제외:
  - 영속 규범
  - 운영 runbook 본문

## 작성 규칙

각 문서는 첫 30초 안에 아래 세 가지를 독자가 알 수 있어야 한다.

1. 이 문서는 어떤 질문에 답하는가?
2. 누구를 위한 문서인가?
3. 규범인가, 운영 가이드인가, 상태 보고인가?

권장 규칙:

- 문서 첫머리에 `목적` 또는 `요약`으로 질문을 명시한다.
- 규범 문서는 현재 구현 상태를 길게 설명하지 않는다. 상태는 [QMTL 구현 추적성](implementation_traceability.md)으로 링크한다.
- 운영 문서는 설계 원칙을 다시 정의하지 않는다. 필요 시 규범 문서로 링크한다.
- 제품 계약 문서는 고급 운영 옵션을 본문 흐름에 섞지 않는다. 별도 “운영자 경로”로 분리한다.
- moved/deprecated 문서는 짧게 유지하고, 현재 문서를 링크하는 데 집중한다.
- nav에 올리지 않을 문서(moved marker, icebox 메모, locale 미완료 초안)는 `mkdocs.yml`의 `not_in_nav`에 명시해 “의도된 비공개 문서”로 분류한다.

## 권장 상위 구조

권장 문서 지도는 다음과 같다.

```text
Getting Started
Product Contracts
Architecture
  Principles
  Normative Architecture
Operations
Implementation Status
Maintenance
Migration
```

현재 `Architecture` 섹션은 유용하지만, 실제로는 `Product Contracts`와 `Implementation Status` 일부를 함께 들고 있다.
장기적으로는 이 둘을 별도 top-level 또는 명확한 하위 섹션으로 분리하는 것이 좋다.

## 기존 문서의 재분류 초안

### 유지

- `design_principles.md` → Principles
- `capability_map.md` → Principles
- `semantic_types.md` → Principles
- `decision_algebra.md` → Principles
- `gateway.md`, `dag-manager.md`, `worldservice.md`, `controlbus.md` → Normative Architecture
- `implementation_traceability.md` → Implementation Status
- `operations/*` → Operations

### 분리 권장

- `architecture.md`
  - 남길 것: 시스템 상위 구조, 계층 경계, Core Loop의 규범적 최소 계약
  - 분리할 것: 배포 프로필, deprecated 경고, 운영 quickstart, migration성 설명
- `core_loop_world_automation.md`
  - 남길 것: 사용자/제품 관점의 Core Loop 계약
  - 분리할 것: scheduler 운용 절차, operator approval 세부, 실제 실행 runbook

### 이동 후보

- moved 상태인 `architecture/sdk_layers.md` 같은 문서는 유지보수/엔지니어링 계층으로만 남긴다.
- 운영 승인/감사 중심 문서는 `architecture/`보다 `operations/`에 두는 편이 일관적이다.

## 문서 간 링크 방향

문서 링크는 가능한 한 다음 방향을 따른다.

```text
Principles
  -> Normative Architecture
    -> Product Contracts
      -> Operations
        -> Implementation Status
```

역방향 링크는 가능하지만, 본문 논리를 역방향에 의존하지 않는다.

예:

- 원칙 문서는 운영 runbook를 설명하지 않는다.
- 운영 runbook는 규범 계약을 재정의하지 않고 링크한다.
- 구현 추적 문서는 설계 계약을 수정하지 않고, “현재 어디까지 구현됐는가”만 기록한다.

## 제안하는 문서 메타데이터

향후에는 front matter에 다음 필드를 점진적으로 도입하는 것을 권장한다.

- `doc_role`: `principles | normative-architecture | product-contract | operations | implementation-status | migration`
- `audience`: `author | operator | contributor | reviewer`
- `normative`: `true | false`

이 필드는 초기에 도구 강제 없이 시작하고, 이후 문서 lint나 nav 검증에 활용할 수 있다.

## 마이그레이션 진행 상태 (2026-04)

- 완료
  - `architecture.md`와 `worldservice.md`에서 제품 계약·운영 링크·구현 상태 링크를 분리하는 1차 정리를 적용했다.
  - Core Loop 사용자 계약은 [Core Loop 계약](../contracts/core_loop.md)과 [월드 라이프사이클 계약](../contracts/world_lifecycle.md)으로 고정했다.
  - `core_loop_world_automation.md`에서 사용자 계약과 운영 런북을 분리하고, submit/golden path는 계약 문서로 이동했다.
  - `implementation_traceability.md`에 control-plane 및 governance concept를 추가했다.
  - `Gateway`/`DAG Manager`/`ControlBus`/`Risk Signal Hub`의 런타임 운영 문맥을 `operations/` 문서로 분리했다.
- 진행 중
  - 최상위 규범 문서(`architecture.md`, `gateway.md`, `dag-manager.md`)를 더 짧은 normative spec으로 축약하고, CLI/rollout/config 절차는 운영 문서로 이동 중이다.
  - nav는 `Architecture / Product Contracts / Operations / Design / Archive` 구조로 재정리했고, Design 섹션은 개별 icebox 문서 대신 [Icebox 인덱스](../design/icebox.md)를 front door로 사용한다.
  - 공식 nav에 올리지 않을 문서는 `not_in_nav`로 명시해 경고 없이 관리하도록 전환 중이다.
  - locale 미완료 문서는 ko/en 쌍이 준비될 때까지 off-nav 상태로 유지하고, 운영상 꼭 필요한 문서부터 ko/en 미러를 보강한다.
- 남은 항목
  - 거대 규범 문서의 예시/부록/운영 세부를 추가로 외부 문서로 밀어내기
  - Implementation Status와 Migration 계층을 nav에서 더 명시적으로 노출하기
  - design/archive/maintenance 문서의 공개 범위를 주기적으로 재분류하기

## 완료 기준

다음 조건을 만족하면 문서 체계 분리가 의미 있게 진행된 것으로 본다.

- 주요 문서를 읽을 때 “이 문서가 규범인지 상태 설명인지”가 즉시 드러난다.
- `Runner.submit` 사용자 계약과 운영자 절차가 별도 경로로 존재한다.
- 구현 상태를 알고 싶을 때 규범 문서를 뒤지지 않아도 된다.
- 설계 원칙 문서를 읽을 때 현재 구현 예외를 함께 학습하지 않아도 된다.

{{ nav_links() }}
