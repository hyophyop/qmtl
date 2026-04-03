---
title: "QMTL Semantic Types"
tags:
  - architecture
  - design
author: "QMTL 팀"
last_modified: 2026-03-06
---

{{ nav_links() }}

# QMTL Semantic Types

## 관련 문서

- [QMTL 설계 원칙](design_principles.md)
- [QMTL Capability Map](capability_map.md)
- [Decision Algebra](decision_algebra.md)
- [아키텍처 용어집](glossary.md)

## 목적

QMTL의 제약은 feature 이름이나 strategy archetype에서 나오지 않아야 한다.
대신 각 값과 상태가 가지는 의미론을 명시하고,
그 의미론을 기준으로 연결 가능성과 금지 규칙을 판정해야 한다.

이 문서는 그 판단 기준이 되는 semantic type을 정의한다.

## 핵심 축

QMTL의 semantic type은 최소한 다음 축을 드러내야 한다.

- causality: `causal` 또는 `delayed`
- mutability: `immutable` 또는 `mutable`
- scope: `global`, `world-scoped`, `domain-scoped`
- replay legality: `replay-safe`, `live-safe`, `replay-only`
- actuation: `passive`, `decision`, `command`

새로운 값 타입은 구현 전에 이 축 위에서 먼저 설명할 수 있어야 한다.

## 기본 semantic type

### CausalStream

Concept ID: `SEM-CAUSAL-STREAM`

현재 시점까지의 정보만 포함하는 스트림이다.
Feature extraction, inference, decision path에서 기본 입력으로 사용한다.

예:

- quotes
- trades
- order book snapshots
- current portfolio observations
- causal features

### DelayedStream

Concept ID: `SEM-DELAYED-STREAM`

미래 정보나 후행 해석이 포함된 스트림이다.
학습과 평가에는 사용할 수 있지만 live decision path에는 직접 연결할 수 없다.

예:

- triple-barrier label output
- realized future return
- ex-post attribution labels

### ImmutableArtifact

Concept ID: `SEM-IMMUTABLE-ARTIFACT`

재현 가능한 방식으로 저장된 읽기 전용 산출물이다.
Feature artifact, label artifact, dataset snapshot, trained model reference가 여기에 속한다.

핵심 속성:

- content-addressable 또는 fingerprint-bound
- cross-domain read 가능
- mutable execution state를 포함하지 않음

### MutableExecutionState

Concept ID: `SEM-MUTABLE-EXECUTION-STATE`

실행 과정에서 변하는 상태다.
Portfolio, open orders, open quotes, inventory, route acknowledgements 등이 여기에 속한다.

핵심 속성:

- world/domain scoped
- cross-domain 공유 금지
- live/operational correctness와 강하게 결합

### DecisionValue

Concept ID: `SEM-DECISION-VALUE`

실행 의도를 나타내는 값이다.
점수, 방향성, position target, order intent, quote intent 등이 포함된다.

DecisionValue는 `CausalStream` 또는 `ImmutableArtifact` 기반 inference 결과여야 하며,
`DelayedStream`에서 직접 유도되어서는 안 된다.

### CommandValue

Concept ID: `SEM-COMMAND-VALUE`

외부 시스템에 실제 행위를 요청하는 값이다.
Order submission, cancel/replace, rebalance apply 등이 여기에 속한다.

CommandValue는 planner와 policy를 거친 뒤에만 생성할 수 있다.

## 연결 가능성 규칙

아래 규칙은 archetype과 무관하게 항상 유지된다.

| From | To | 허용 여부 | 이유 |
| --- | --- | --- | --- |
| CausalStream | Inference | 허용 | causal input |
| DelayedStream | Inference(live path) | 금지 | 미래 정보 누수 |
| DelayedStream | Dataset Build | 허용 | 연구/평가 전용 |
| ImmutableArtifact | Inference | 허용 | 재현 가능한 read-only input |
| MutableExecutionState | Cross-domain reuse | 금지 | domain isolation 위반 |
| DecisionValue | Planner | 허용 | 공통 execution planning 경계 |
| CommandValue | Direct feature input | 금지 | 실행 부작용을 feature로 역류시키지 않음 |

## World/Domain 규칙

### ImmutableArtifact만 공유 가능

Cross-domain 재사용은 immutable artifact에 한정한다.
실행 캐시와 execution state는 world/domain scoped로 유지한다.

### Mutable state는 SSOT 경계에 종속

MutableExecutionState는 world/domain 및 service boundary에 종속된다.
따라서 동일한 값처럼 보여도 SSOT 경계를 넘는 순간 같은 객체로 취급하지 않는다.

### Replay legality는 타입 수준에서 고정

값이 replay-only인지 live-safe인지는 호출 시점에 ad hoc하게 판단하지 않고,
semantic type의 일부로 미리 선언해야 한다.

## 새 타입 추가 절차

새 semantic type이나 value family를 추가할 때는 아래를 문서에 먼저 적는다.

1. 이 값은 causal인가 delayed인가?
2. immutable인가 mutable인가?
3. world/domain scope는 무엇인가?
4. live-safe인가 replay-only인가?
5. decision, state, artifact, command 중 어디에 속하는가?

이 다섯 질문에 답하지 못하면,
구현보다 먼저 semantic contract 정의를 보완해야 한다.

## 설계 기준

좋은 설계는 다음을 만족한다.

- 금지 규칙을 strategy name이 아니라 semantic type으로 설명할 수 있다.
- 새 feature를 추가해도 legality matrix의 일부로 흡수된다.
- `ML + MM` 같은 조합도 semantic type만 맞으면 특례 없이 연결된다.

나쁜 설계의 신호는 다음과 같다.

- `if strategy_type == "mm"`가 legality를 결정한다.
- `if live and ml and labels` 같은 조합 특례가 필요하다.
- 값의 의미론보다 payload shape가 규칙을 결정한다.

{{ nav_links() }}
