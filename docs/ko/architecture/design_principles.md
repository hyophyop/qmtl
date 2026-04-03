---
title: "QMTL 설계 원칙"
tags:
  - architecture
  - design
author: "QMTL 팀"
last_modified: 2026-03-06
---

{{ nav_links() }}

# QMTL 설계 원칙

## 관련 문서

- [아키텍처 개요](architecture.md)
- [Capability Map](capability_map.md)
- [Semantic Types](semantic_types.md)
- [Decision Algebra](decision_algebra.md)
- [아키텍처 용어집](glossary.md)

## 목적

QMTL의 목적은 특정 전략 archetype을 위한 전용 프레임워크를 만드는 것이 아니라,
새로운 전략 방식·학습 방식·실행 방식이 추가되어도 예외 처리의 집합으로 붕괴하지 않는
**엄밀한 조합 가능 시스템**을 제공하는 것이다.

따라서 QMTL 설계는 “현재 기능을 잘 설명하는 구조”만으로 충분하지 않다.
새 기능이 들어올 때마다 아래 질문에 안정적으로 답할 수 있어야 한다.

- 이 기능은 기존 capability와 자연스럽게 조합되는가?
- 조합을 위해 조합별 특례가 필요한가?
- 제약은 feature 이름이 아니라 의미론으로 설명되는가?
- 새 기능은 기존 코어 규칙을 유지한 채 contract 추가로 수용되는가?

이 질문에 반복적으로 “예외적으로 그렇다”라고 답하게 된다면,
그것은 기능 부족이 아니라 설계 결함의 신호로 간주한다.

## 1급 규칙

### 1. Capability-first

Concept ID: `PRIN-CAPABILITY-FIRST`

QMTL의 1급 개념은 `directional`, `ML`, `market making` 같은 archetype이 아니라
다음과 같은 독립 capability여야 한다.

- 관측
- 특징 추출
- 라벨링
- 추론
- 의사결정
- 실행 계획
- 실행 상태
- 위험/정책

전략 archetype은 위 capability의 조합으로만 설명되어야 하며,
코어 설계의 기준 축이 되어서는 안 된다.

### 2. Composition Over Exceptions

Concept ID: `PRIN-COMPOSITION-OVER-EXCEPTIONS`

기능 조합은 특수 사례가 아니라 기본 사용 방식이어야 한다.
예를 들어 `ML + Market Making`, `Rule-based + Quote Planning`,
`Labeling + Offline Replay` 같은 조합은 별도 특례가 아니라
기존 capability의 합성으로 설명되어야 한다.

조합을 위해 다음과 같은 분기가 필요해지면 설계를 다시 검토한다.

- `if strategy_type == ...`
- `if mm_enabled and ml_enabled`
- 도메인/전략 유형 조합별 특례 경로

### 3. 제약은 의미론에서 나온다

Concept ID: `PRIN-SEMANTIC-CONSTRAINTS`

어떤 조합이 허용되지 않는 이유는
“이것이 ML이라서”, “이것이 MM이라서”가 아니라
값과 단계의 의미론 때문이어야 한다.

예:

- 미래 정보를 포함한 값은 live decision path에 투입할 수 없다.
- mutable execution state는 cross-domain 공유할 수 없다.
- immutable artifact만 재현 가능한 방식으로 cross-domain read를 허용할 수 있다.

따라서 시스템의 금지 규칙은 feature 이름이 아니라 semantic type으로 기술한다.

### 4. Core Neutrality

Concept ID: `PRIN-CORE-NEUTRALITY`

Core는 특정 전략 스타일을 암묵적으로 특권화하면 안 된다.
Directional 전략이 먼저 구현되었다는 이유로 모든 실행 개념이 `order` 중심으로 고정되면,
후속 `quote`, `inventory`, `cancel/replace` 개념이 들어올 때 구조 왜곡이 발생한다.

Core는 특정 전략을 잘 설명하는 구조가 아니라,
서로 다른 실행 형태를 같은 수준의 엄밀함으로 수용할 수 있는 구조여야 한다.

### 5. Explicit Research/Execution Boundaries

Concept ID: `PRIN-EXPLICIT-BOUNDARIES`

QMTL은 연구·평가·실행을 모두 다룰 수 있지만,
서로 다른 경계의 값을 암묵적으로 섞어서는 안 된다.

특히 다음 경계는 항상 명시적이어야 한다.

- causal vs delayed
- replay-only vs live-safe
- immutable artifact vs mutable state
- decision output vs execution state

이 경계가 흐려질수록 기능 추가 시 누수와 조합별 특례가 증가한다.

### 6. Extension Adds Contracts

Concept ID: `PRIN-EXTENSION-ADDS-CONTRACTS`

좋은 확장은 기존 분기 수를 늘리지 않는다.
대신 새 semantic type, 새 decision subtype, 새 planner, 새 adapter를 추가하고
기존 단계 계약은 유지한다.

새 기능은 가능하면 새 top-level mode나 새 archetype enum이 아니라
기존 capability graph 안의 어디에 놓이는지 먼저 설명할 수 있어야 한다.

### 7. Profiles Are Examples

Concept ID: `PRIN-PROFILES-ARE-EXAMPLES`

`ML-driven MM`, `directional trend`, `label research` 같은 profile은
문서화와 온보딩을 위한 예시일 뿐,
코어 타입 체계나 서비스 경계를 규정하는 1급 개념이 아니다.

Profile이 늘어나도 코어 규칙은 늘어나지 않아야 한다.

## 설계 판단 체크리스트

새 기능이나 변경이 들어올 때는 아래 순서로 검토한다.

1. 이 기능은 어떤 capability에 속하는가?
2. 이 기능의 입력과 출력은 어떤 semantic type을 가지는가?
3. 기존 capability와 조합될 때 새 특례 없이 설명되는가?
4. 금지 규칙이 있다면 feature 이름이 아니라 의미론으로 기술되는가?
5. 새 기능은 기존 코어를 바꾸는가, 아니면 새 contract를 추가하는가?

위 질문 중 3번과 4번에 반복적으로 실패하면,
구현보다 capability 경계와 semantic contract를 먼저 수정한다.

## 비목표

QMTL은 모든 전략을 하나의 동일한 실행 모델로 억지 통합하는 것을 목표로 하지 않는다.
대신 서로 다른 전략이 공통 capability와 semantic contract 위에서
공존하고 조합될 수 있도록 하는 것을 목표로 한다.

따라서 “모두 비슷하게 보이게 만드는 것”보다
“모두 같은 규칙 아래에서 합성 가능하게 만드는 것”이 우선이다.

{{ nav_links() }}
