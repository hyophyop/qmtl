---
title: "SDK 자동 returns 설계 비교 메모"
tags: [design, returns, validation, sr]
author: "QMTL Team"
last_modified: 2025-11-29
status: draft
---

# SDK 자동 returns 설계 비교 메모

## 0. As‑Is / To‑Be 요약

- As‑Is
  - 이 문서는 여러 auto_returns 설계 초안을 비교하는 임시 메모이며, `Runner.submit`에 기본적인 opt-in 구현이 도입되었지만 노드/필드/계산 방식을 세밀하게 제어하는 확장안은 아직 열려 있습니다.
- To‑Be
  - `auto_returns_unified_design.md`에 정리된 통합 설계안을 기준으로, 이 비교 문서는 역사적/의사결정 맥락을 보존하는 참고 자료로 유지됩니다.
  - 상단 As‑Is 설명을 통해, 독자가 이 문서를 읽을 때 언제나 설계 vs 구현 상태를 구분할 수 있도록 합니다.

> **비교 대상 문서**
> - SDK 전반 설계: [`auto_derive_returns_proposal.md`](./auto_derive_returns_proposal.md)  
> - SR 경로 초점 스케치: [`sr_auto_returns_integration_sketch.md`](./sr_auto_returns_integration_sketch.md)

이 문서는 QMTL SDK에서 **자동 수익률(returns) 파생**을 지원하기 위한 두 설계 초안의 성격과 장단점을 비교하는 임시 메모입니다.

## 1. 공통 전제

두 문서는 모두 다음 전제를 공유합니다.

- 기본 동작은 유지하고, 자동 returns 파생은 **opt-in 옵션**으로만 동작해야 한다.
- 전략이 명시적으로 `returns`/`equity`/`pnl`을 제공하는 경우 **항상 그 값을 우선** 사용해야 한다.
- ValidationPipeline/WorldService는 여전히 “이미 계산된 returns를 입력받아 사용한다”는 계약을 유지하는 것이 바람직하다.
- 가격 기반 단순 전략(특히 피드/데모/스모크용)에서 **returns 배선 보일러플레이트를 줄이는 것**이 주요 목표다.

## 2. `auto_derive_returns_proposal.md` (SDK 전반 설계) 장단점

### 장점

- **SDK 전체 관점에서의 완결성**
  - Runner.submit, ValidationPipeline, 새 유틸 모듈(`returns_derive.py`)까지 포함해 **end-to-end 수준의 API/구현 스케치**를 제공한다.
  - `_extract_returns_from_strategy` 확장, `SubmitResult.returns_source` 메타데이터 등 **관측성**까지 포함해 설계 범위가 넓다.
- **구체적인 API 제안**
  - `auto_derive_returns: bool | str | None`, `returns_field`, `derive_returns_from_price_node(...)` 등 **구현에 바로 옮기기 쉬운 시그니처**를 제시한다.
  - ValidationPipeline 생성자에도 동일 옵션을 두어, Runner를 거치지 않는 직접 검증 플로우까지 고려한다.
- **테스트/체크리스트 제공**
  - 실제 작업 시 따라갈 수 있는 구현 체크리스트가 있어, **작업 범위와 영향도를 파악하기 쉽다.**

### 단점 / 열어둔 이슈

- **표현력이 다소 제한적인 API**
  - `auto_derive_returns: bool | str` 패턴은 단순하고 직관적이지만, 노드/필드/계산방식/제약조건 등을 세밀하게 조합하기에는 확장성이 아쉽다.
  - 향후 옵션이 늘어나면 개별 인자를 추가하거나 문자열 프로토콜을 확장해야 해서, **API가 빨리 복잡해질 위험**이 있다.
- **ValidationPipeline까지 파라미터 침투**
  - ValidationPipeline 생성자에 새 파라미터를 추가하면서 **계약 표면적이 넓어지고**, auto-derive 기능이 런타임/Runner 레이어를 넘어 검증 계층에까지 퍼질 수 있다.
  - 실제로는 Runner.submit에서 returns를 결정한 뒤 ValidationPipeline에는 “이미 계산된 returns”만 넘기는 편이, 설계가 더 깔끔할 수 있다.
- **SR/Seamless 맥락과는 분리된 관점**
  - 문서 자체는 일반적인 SDK 사용자를 대상으로 설계되어 있어, **SR 통합(Seamless Provider, ExpressionDagBuilder 등)과의 접점을 명시적으로 다루지는 않는다.**

## 3. `sr_auto_returns_integration_sketch.md` (SR × Runner.submit 스케치) 장단점

### 장점

- **SR/Seamless 경로에 특화된 맥락**
  - SR 통합 문서(`sr_integration_proposal.md`)와 직접 연결되어, **표준 price 노드/Seamless Data Provider/Expression DAG**를 전제로 한 설계가 가능하다.
  - SR 템플릿이 Runner.submit 호출 시 적절한 `auto_returns` 설정을 주입하는 그림이 명확해, **SR에서의 사용 스토리가 구체적**이다.
- **보다 유연한 설정 모델**
  - `auto_returns: bool | AutoReturnsConfig | None` 패턴과 `AutoReturnsConfig(node, field, method, min_length, ...)` 스케치는,
    - 노드명/필드/계산 방식/제약조건 등을 **구조적으로 확장 가능**한 형태로 묶는다.
  - 향후 log-return, 여러 노드 조합 등으로 확장하기 수월하다.
- **계층 분리 강조**
  - auto-returns를 Runner.submit 측 전처리 레이어에 한정하고, ValidationPipeline/WorldService 계약은 그대로 유지하자는 방향을 명확히 잡고 있다.
  - 이는 **설계 변경 반경을 좁게 유지하는 데 유리**하다.

### 단점 / 열어둔 이슈

- **구현 디테일은 상대적으로 느슨**
  - SDK 전반의 정확한 시그니처/모듈 구조까지는 정의하지 않고, 개념적인 `AutoReturnsConfig`, `derive_returns_from_price(...)` 정도만 스케치한다.
  - 실제 구현 시에는 여전히 `auto_derive_returns_proposal.md` 수준의 디테일 설계가 필요하다.
- **SDK 일반 사용 사례에 대한 서술 부족**
  - 주로 SR/Seamless 관점(표준 price 노드, Expression DAG)에 초점을 맞추고 있어,
  - **일반적인 수동 전략/백테스트 사용자**에게 auto-returns를 어떻게 노출할지에 대한 논의는 상대적으로 적다.

## 4. 종합 비교 및 조합 아이디어

요약하면:

- `auto_derive_returns_proposal.md`
  - 장점: SDK 전반을 포괄하는 **구체적이고 실행 가능한 설계**, 체크리스트까지 포함.
  - 단점: API 확장성이 제한적이고, ValidationPipeline 계층까지 영향이 퍼질 위험.
- `sr_auto_returns_integration_sketch.md`
  - 장점: **SR/Seamless 맥락에 최적화**, 유연한 Config 모델, 계층 분리 강조.
  - 단점: 구현 디테일은 비교적 느슨하고, 일반 SDK 플로우에 대한 서술이 적음.

실제 구현 시에는 두 문서를 다음과 같이 조합하는 방향이 자연스러워 보입니다.

- API/모듈 구조는 **`auto_derive_returns_proposal.md`의 구체적인 시그니처·체크리스트를 기반으로 하되**,  
- 옵션 모델과 SR 통합 관점은 **`sr_auto_returns_integration_sketch.md`의 `AutoReturnsConfig`/Runner 전처리 레이어 아이디어**를 채택하는 식으로 병합.

이 메모는 두 설계 초안의 위치와 역할을 정리하기 위한 임시 문서이며, 최종 구현 결정이 내려지면 관련 내용을 각 본문 설계 문서에 흡수/정리하는 것이 좋습니다.

## 5. 사용자 피드백 선순환 관점 비교

여기서는 “QMTL 사용자가 지표를 피드백 삼아 전략을 개선·재제출하고, 개선된 지표를 확인하면서 선순환을 만드는 데 얼마나 효과적인지”라는 축에서 두 설계를 비교합니다.

### 5.1 선순환을 구성하는 요소

지표 기반 선순환이 잘 작동하려면 대략 다음 조건이 필요합니다.

- **저마찰 첫 제출(on-ramp)**: “일단 제출해서 무언가 지표를 보는 것”까지의 진입 장벽이 낮을 것.
- **피드백 지표의 품질(fidelity)**: 자동 파생 returns라도, 전략의 실제 행동과 어느 정도 상관된 지표여야 사용자가 개선 방향을 해석할 수 있음.
- **점진적 고도화 경로(upgrade path)**: 초기에 auto-returns에 의존하더라도, 나중에 명시적 `returns`/`equity`/`pnl`로 자연스럽게 이행할 수 있는 경로가 있을 것.
- **관측성과 설명 가능성(observability)**: 사용자가 “이 지표가 어디서 온 것인지(derived vs explicit)”를 쉽게 알 수 있어야, 잘못된 피드백 루프를 줄일 수 있음.

### 5.2 `auto_derive_returns_proposal.md` 관점

**장점 (선순환에 유리한 점)**

- Runner/ValidationPipeline 전반에서 자동 파생 경로를 제공하므로, **어떤 타입의 전략이든 “일단 지표를 보는” 초기 제출을 빠르게 만들 수 있습니다.**
- `SubmitResult.returns_source`와 같은 메타데이터를 노출하는 설계는,  
  - 사용자가 “이번 결과가 명시적 returns인지, auto-derived인지”를 알 수 있게 해 주어,
  - 잘못된 지표에 과신하는 리스크를 줄이는 데 도움을 줍니다.
- ValidationPipeline 레벨에서 옵션을 받을 수 있기 때문에,  
  - **실험용 파이프라인**(예: “auto-derive 허용 스모크 전용 preset”)과  
  - **실전용 파이프라인**(명시적 returns만 허용)을 구분해 구성하기 쉬워,  
  - 사용자의 학습 곡선을 설계/문서화하기에 좋습니다.

**단점 / 주의점**

- ValidationPipeline까지 auto-derive 옵션이 침투하면,
  - 팀 내에서 “어디까지가 공식 지표이고 어디부터는 스모크용 지표인지”에 대해 혼동이 생길 수 있고,
  - 일부 사용자는 auto-derive 기반 지표만 보고 전략을 최적화하려 할 위험이 있습니다.
- `auto_derive_returns: bool | str` 수준의 API는 쉬운 대신,
  - 전략 구조에 맞춘 더 정교한 파생 규칙을 만들기 어려워,
  - **지표 fidelity 측면에서는 다소 거친 피드백 루프**를 만들 가능성이 있습니다.

**결론적으로**, 이 설계는 “넓은 사용자 풀에 대해 빠르게 지표를 보여주는 역할”에는 강하지만,  
SR/표현식 기반 전략처럼 구조가 일정한 집단에 대해 **조금 더 정교한, 전략 구조에 맞춘 피드백 루프**를 만들기에는 부족한 면이 있습니다.

### 5.3 `sr_auto_returns_integration_sketch.md` 관점

**장점 (선순환에 유리한 점)**

- SR/Seamless 경로에 특화되어 있어,
  - ExpressionDagBuilder와 Seamless Provider가 만드는 **표준 price 노드**에 맞춰 `AutoReturnsConfig`를 설계할 수 있습니다.
  - 이는 SR이 생성하는 후보 전략들이 **비슷한 방식으로 returns가 파생되는 공통 기준**을 가지게 함을 의미합니다.
- 공통 기준이 있다는 것은,
  - SR가 여러 세대에 걸쳐 후보를 생성 → Runner.submit + auto-returns로 검증 → fitness/metrics 피드백을 다시 SR로 돌려보낼 때,
  - **지표가 서로 비교 가능하게 유지**된다는 뜻이라, 전략 개선 선순환을 만들기 쉽습니다.
- `AutoReturnsConfig` 같은 구조화된 설정을 쓰면,
  - 초기에 “단순 pct_change 기반 returns”로 시작하되,
  - 나중에 config만 바꾸어 “보다 실제 PnL에 가까운 파생 로직”으로 점진적 고도화가 가능해,
  - **“빠른 on-ramp → 점진적 fidelity 향상” 경로를 설계하기 용이**합니다.

**단점 / 주의점**

- SR 경로에 초점이 맞춰져 있어서,
  - 일반적인 수동 전략 사용자는 “SR에서 쓰는 auto-returns”와 “직접 작성하는 전략의 returns” 사이의 차이를 이해하기 어려울 수 있고,
  - UI/문서에서 이 차이를 잘 설명하지 않으면 **지표 해석 혼선**이 생길 여지가 있습니다.
- auto-returns가 “SR 템플릿에서 자동으로 켜지는 옵션”이 되면,
  - 사용자 입장에서는 지표가 어디서 파생되었는지 인지하지 못한 채,
  - derived metrics를 곧바로 최적화 대상으로 삼을 수 있어,  
  - 실전 PnL과의 괴리가 커질수록 피드백 루프 품질이 떨어질 수 있습니다.

**결론적으로**, 이 설계는 “SR·표현식 기반 전략 집단 내부에서 **비교 가능한 지표를 반복 측정**하며 개선해 나가는 선순환”을 만드는 데 강점이 있습니다.  
다만, auto-returns의 존재와 한계를 사용자에게 충분히 노출하지 않으면, **파생 지표에 대한 과신**으로 이어질 수 있습니다.

### 5.4 선순환 관점에서의 조합 제안

사용자 피드백 선순환을 극대화하려면 두 설계를 다음과 같이 조합하는 것이 좋아 보입니다.

- **on-ramp 및 관측성**
  - `auto_derive_returns_proposal.md`에서 제안한 `returns_source` 등 메타데이터는 반드시 포함시켜,  
    - Runner/World UI, 로그, 리포트에서 **“이번 지표는 derived인지 explicit인지”를 항상 보여주도록** 합니다.
  - 스모크/데모용 preset에서는 auto-returns를 허용하되,  
    - 실전/프로덕션 preset에서는 **명시적 returns만 허용**하도록 정책을 구분하면,
    - 사용자에게 자연스러운 “연습 → 실전” 단계적 피드백 루프를 제공할 수 있습니다.

- **SR 집단에 특화된 비교 가능성**
  - `sr_auto_returns_integration_sketch.md`의 `AutoReturnsConfig`를 SR 템플릿에 적용해,
    - SR에서 나오는 후보 전략들은 공통 규약으로 returns가 파생되도록 맞춥니다.
  - 이렇게 하면 SR 후보군 내에서는 **지표 비교가 공정하고 일관되게 유지**되고,
    - 사용자는 “동일한 파생 규칙 아래에서 성능이 개선되는지”를 반복 측정할 수 있습니다.

- **점진적 고도화 경로**
  - SR/피드 기반 전략에 대해:
    1. 1단계: auto-returns 기반 지표로 빠른 탐색/필터링.
    2. 2단계: 일정 기준을 넘는 후보들에는 명시적 `returns`/`equity`/`pnl`을 도입하도록 가이드.
    3. 3단계: 실전 World/preset에서는 explicit returns를 필수로 요구.
  - 이 흐름을 문서/가이드에 녹이면,
    - 사용자는 초기에는 **낮은 비용으로 지표를 보고**,  
    - 의미 있는 후보를 추렸을 때 **고품질 지표를 향해 자연스럽게 업그레이드**하는 선순환을 경험할 수 있습니다.

요약하면,  
- 넓은 사용자층과 다양한 전략 타입에 대한 “지표 on-ramp + 관측성” 측면에서는 `auto_derive_returns_proposal.md`가,  
- SR/표현식 기반 전략 집단에 대한 “비교 가능한 반복 측정” 측면에서는 `sr_auto_returns_integration_sketch.md`가 더 유리합니다.  
두 설계를 함께 사용하는 것이, 지표를 기반으로 전략을 반복 개선하는 **실질적인 선순환**을 만드는 데 가장 효과적입니다.
