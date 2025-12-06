---
title: "QMTL 아키텍처 문서 재작성 가이드 (보관용)"
tags: [architecture, design, docs, archive]
author: "QMTL Team"
last_modified: 2025-12-01
status: archived
---

# QMTL 아키텍처 문서 재작성 가이드 (보관용)

!!! info "보관 상태"
    이 문서는 2025‑Q4 아키텍처 문서 개편 작업을 위한 임시 가이드였습니다.  
    주요 내용은 `docs/ko/architecture/architecture.md`, `docs/ko/architecture/worldservice.md`,  
    `docs/ko/architecture/gateway.md`, `docs/ko/architecture/seamless_data_provider_v2.md`,  
    `docs/ko/world/world.md` 등에 반영되었으며, 이 파일은 역사적 참고용으로만 유지됩니다.

# QMTL 아키텍처 문서 재작성 가이드 (As‑Is / To‑Be)

이 문서는 QMTL v2.0까지 구현된 내용을 **현재 상태(As‑Is)** 기반으로 정리하고,  
사용자가 원하는 **핵심 경험(To‑Be)**을 기준으로 아키텍처/설계 문서를 어떻게 재구성할지에 대한 가이드를 제시한다.

- 대상 문서:
  - 아키텍처 개요: `docs/ko/architecture/architecture.md`
  - 월드/정책: `docs/ko/world/world.md`
  - 단순화 제안: `./simplification_proposal.md`
  - Auto Returns: `./auto_returns_unified_design.md` (통합안)
  - SR 통합: `./sr_integration_proposal.md`

이 가이드는 **완전한 구현이 아직 없는 상태에서도**,  
문서 구조를 “목표 경험을 기준으로” 재정렬할 수 있도록 As‑Is/To‑Be를 함께 드러내는 것을 목표로 한다.

---

## 0. 목표: 문서의 북극성 정렬

사용자가 기대하는 QMTL의 핵심 경험은 다음 한 줄로 요약된다.

> 전략 작성 → 제출 → (시스템이 알아서 평가/배포) → 월드 수익률 증가 확인 → 전략 개선

이를 좀 더 구체화하면 네 가지 축으로 나뉜다.

1. **Replay 기반 백테스트**  
   - 어떤 데이터를 쓰든 “월드 안에서의 시장 상황 replay”로 전략을 검증할 수 있어야 한다.
2. **데이터 공급 자동화**  
   - 전략 코드는 “어떤 데이터가 필요하다”만 표현하고, 실제 공급/백필/라이브 전환은 프레임워크가 책임진다.
3. **성과 자동 평가 → 자동 tradable 전환**  
   - 제출만 하면 시스템이 백테스트, 지표 계산, 정책 검증, 활성/비활성 판단까지 수행한다.
4. **월드 단위 자본 자동 배분**  
   - 월드는 전략 성과/상관/리스크에 따라 자본을 자동으로 재배분하고, 사용자는 결과만 확인하며 전략을 개선한다.

이 문서는 위 4축 각각에 대해:

- **As‑Is:** 현재 구현과 제약을 요약하고
- **To‑Be:** 목표 경험을 위해 어떤 설계/기능이 필요하며
- **Docs:** 어떤 설계 문서에서 어떻게 드러내야 하는지

를 정리한다.

---

## 1. Core Loop 관점에서의 As‑Is 요약

### 1.1 Replay 백테스트 (데이터 → 히스토리 → DAG 실행)

- **As‑Is**
  - `HistoryWarmupService`  
    (`qmtl/runtime/sdk/history_warmup_service.py`)가 `StreamInput` 노드의 히스토리를 로드하고,  
    `Pipeline`을 통해 타임스탬프 순서대로 replay 한다.
  - 데이터 공급은 `SeamlessDataProvider` + `HistoryProvider` 추상화로:
    - 캐시 → 스토리지 → 백필 → 라이브 순으로 시도하는 구조가 구현돼 있다.
    - 로컬 개발용으로 `InMemorySeamlessProvider`를 사용하면 CSV/DataFrame도 같은 경로를 탄다.
  - 다만 “world만 지정하면 알아서” 수준은 아니고:
    - 전략 안에서 `StreamInput(interval, period, history_provider=...)`를 명시해야 하고,
    - `dataset_id`, `snapshot_version` 등 데이터셋 메타를 사용자가 설계 수준에서 이해하고 채워 넣어야 한다.

- **한계**
  - Replay 엔진 자체는 존재하지만, **데이터 선택/연결**은 여전히 사용자 책임이 크다.
  - `ComputeContext / dataset_fingerprint / as_of`는 잘 설계되어 있으나, 기본 on‑ramp에선 과도한 개념 노출이다.

### 1.2 데이터 공급 자동화

- **As‑Is**
  - `SeamlessDataProvider`는 “캐시 → 히스토리 → 백필 → 라이브”를 한 추상화 안에서 다루도록 설계되고 구현돼 있다.
  - 월드 문서(`docs/ko/world/world.md`)에서도 기본 데이터 핸들러로 명시되어 있고,
  - IO 계층에는 `EnhancedQuestDBProvider`, `InMemorySeamlessProvider` 등 구체 구현과 헬퍼가 있다.

- **한계**
  - Runner/SDK 관점에서 “world만 지정하면 적절한 Seamless provider를 전략에 꽂아준다”는 계약은 없다.
    - SR 템플릿(`build_strategy_from_dag_spec`)은 `history_provider` 인자를 반드시 요구한다.
    - 일반 Strategy에서도 provider를 직접 구성하거나 예제를 따라야 한다.
  - `qmtl.yml`, conformance, backfill, fingerprint 모드 등은 강력하지만,
    기본 유저 플로우에서 노출되는 옵션이 많아 “데이터는 시스템이 알아서”라는 인상을 약화시킨다.

### 1.3 성과 자동 평가 → tradable 전환

- **As‑Is**
  - `Runner.submit / submit_async` 경로:
    - world/preset/정책을 해석 (`_get_default_world`, `_fetch_world_description`, presets).
    - `HistoryWarmupService.warmup_strategy(...)`로 히스토리 로드 + replay.
    - `ValidationPipeline`으로 Sharpe, MDD, win_rate, profit_factor, 선형성 지표 계산 후 정책에 따라 PASS/FAIL 판단.
    - 필요 시 `GatewayClient.evaluate_strategy`를 통해 `/worlds/{world}/evaluate`에 한 번 더 묻는다.
  - WorldService:
    - `DecisionEvaluator + Policy` DSL + 활성 집합 관리(Activation)가 구현돼 있다.
    - 별도 할당/리밸런싱 엔진 (`worldservice.rebalancing.*`, `upsert_allocations`)이 존재해,
      world 단위 자본 배분 계획을 만들 수 있다.
  - 라이브 전환:
    - `ActivationManager`가 Gateway `events/subscribe`를 통해 활성 테이블을 받아오고,
    - `execution_nodes.activation_blocks_order`에서 주문 게이트 역할을 한다.

- **핵심 부족/불연결**
  - **auto_returns 미구현**
    - 설계 문서(`./auto_returns_unified_design.md`)의 `AutoReturnsConfig`, `auto_returns` 파라미터, `returns_derive.py`는 코드에 없다.
    - 실제 `submit_async`는
      - 인자로 받은 `returns`, 또는
      - `_extract_returns_from_strategy`로 `strategy.returns / equity / pnl`만 본다.
    - 이 둘이 모두 비어 있으면 `auto_validate=True`일 때 바로 `"No returns produced"`로 거절된다.
    - SR 기반 전략(`build_expression_strategy`, `build_strategy_from_dag_spec`)은 기본적으로 returns를 만들지 않으므로,
      현재 상태에선 Runner.submit + auto‑validate와 맞지 않는다.
  - **WorldService 평가 ↔ 활성화/자본 배분 연결**
    - `/worlds/{world}/evaluate` 응답 모델(`ApplyResponse`)은 `active: [strategy_id]`만 포함한다.
    - SDK의 `_parse_ws_eval_response`는 `weights`, `contributions`, `ranks`도 기대하지만,
      현재 스키마/구현로는 거의 항상 `None`에 가깝다.
    - 실제 자본 배분/리밸런싱은 `upsert_allocations` 경로에서 처리되며,
      이는 Runner.submit과 분리된 운영 플로우(positions, total_equity, run_id 필요)다.
    - Activation(게이트 ON/OFF) 역시 `/apply` 또는 `PUT /activation`으로 갱신되며, Runner.submit이 직접 호출하지 않는다.

### 1.4 전략 개발 → 월드 내 평가 결과 조회 → 개선 루프

- **As‑Is**
  - `SubmitResult`는 `status`, `metrics`, `contribution`, `weight`, `rank`, `improvement_hints`를 잘 정리해 돌려준다.
  - CLI `qmtl submit`도 이를 그대로 출력하도록 설계되어 있어, “한 번 제출했을 때 받는 피드백”은 충분히 구조화되어 있다.

- **한계**
  - Returns가 없으면 아예 Validation으로 못 넘어가기 때문에,
    사실상 “전략 로직만 작성 → 제출”이 아니라 “returns/equity/pnl까지 구현하거나, submit에 returns를 넘겨야” 한다.
  - SR 템플릿의 `submit_with_validation`은 “표본 검증 → 임의 submit_fn 호출” 수준으로,
    Runner.submit 파이프라인과는 아직 느슨하게만 연결되어 있다.

---

## 2. 사용자 관점에서 과도하게 복잡한 지점 (정리)

As‑Is 분석을 바탕으로, 핵심 복잡도 요인은 다음 세 가지로 요약된다.

1. **성과 평가 / 활성화 / 자본 배분이 세 레이어로 분리**
   - SDK `ValidationPipeline`(로컬) ↔ WorldService `/evaluate` ↔ WorldService `upsert_allocations`.
   - 서로 다른 모델과 엔드포인트를 사용해 “세계관 1개”로 느끼기 어렵다.
2. **데이터/컨텍스트 관련 개념 노출 과다**
   - Seamless, conformance, backfill, fingerprint, compute_context, dataset_fingerprint, as_of …  
     등 내부 최적화/감사용 개념이 사용자 문서에도 많이 드러난다.
3. **World / Policy / Mode 개념이 흩어져 있음**
   - `Mode(backtest/paper/live)`, ExecutionDomain, WorldPolicy preset, gating policy YAML 등이
     Runner, WorldService, Gateway 문서에 각각 흩어져 있어,
     전체 그림을 이해하려면 여러 문서를 동시에 읽어야 한다.

이 문서의 To‑Be 제안은, 위 세 지점을 **“Core Loop 기준으로 재배열된 문서 구조”**로 흡수하는 것이다.

---

## 3. To‑Be: 핵심 기능 및 설계 방향

### 3.1 P0 — auto_returns 실제 구현 및 노출

- **목적**
  - “데이터만 연결하면, 기본적인 백테스트 성과는 시스템이 알아서 계산한다”는 약속을 지키기 위한 최소 기능.

- **설계 방향**
  - `Runner.submit/submit_async` 시그니처에 `auto_returns` 옵션 추가  
    (타입은 `AutoReturnsOption = bool | str | AutoReturnsConfig | None`).
  - `ValidationPipeline`은 그대로 “이미 계산된 returns만 입력받는” 계약을 유지한다.
  - `submit_async` 전처리에서:
    1. 명시적 `returns` 인자 → 최우선 사용
    2. `strategy.returns/equity/pnl` → 다음 우선순위
    3. 둘 다 없고 `auto_returns`가 truthy면:
       - HistoryWarmup과 DAG 실행 결과에서 가격 스트림(`StreamInput`)을 찾아
       - pct_change/log_return 기반 `backtest_returns`를 자동 파생
       - 실패 시에는 “파생 실패”를 improvement_hint로 남기고, 기존 동작(returns 없음)에 맞춰 거절

- **문서 반영**
  - `./auto_returns_unified_design.md`를 업데이트해:
    - Runner.submit 전처리 레이어만 확장하고
    - ValidationPipeline 계약은 그대로 유지한다는 점을 명시
    - SR 통합 설계(`./sr_integration_proposal.md`)와 auto_returns 연결 지점을 Core Loop 기준으로 설명

### 3.2 P0 — 평가/활성화/자본 배분의 단일 표면 정의

- **목적**
  - 사용자가 Runner.submit/CLI만 보고도,
    “이 전략이 world에서 어느 정도 비중/기여로 운용될지”를 이해할 수 있게 만들기.

- **설계 방향**
  - **외부 계약:** WorldService가 최종 active/weight/contribution의 source of truth.
  - SDK `ValidationPipeline`은:
    - 로컬에서 “정책 기준으로 통과 가능한지”와
    - “개선 힌트”를 계산하는 **보조 레이어**로 위치를 조정.
  - Runner.submit 경로는:
    1. returns/metrics 계산 → ValidationPipeline으로 **로컬 사전 검사** (필요 시)
    2. WorldService `/evaluate`로 **최종 결정** 요청
    3. SubmitResult에는 WorldService 결과를 우선 사용하고, 로컬 결과는 힌트/참고로만 포함

- **문서 반영**
  - `docs/ko/world/world.md`에 “World‑First Core Loop” 섹션 추가:
    - 입력: metrics + returns
    - 처리: Policy 평가 → active set 결정
    - 출력: active 목록 + (선택) weight/contribution
  - `./simplification_proposal.md`에는
    - “ValidationPipeline은 WorldService 평가의 축소 버전”이라는 관계를 명시.

### 3.3 P1 — 월드 정책 → 활성화 → 리밸런싱 플로우의 표준 루프화

- **목적**
  - “전략 제출만 하면 월드가 알아서 좋은 전략만 켜고, 자본도 재배분한다”는 서사를  
    실제 WorldService API + CLI 흐름으로 명확히 드러내기.

- **설계 방향(개념 수준)**
  1. **평가 루프**
     - Runner/배치가 주기적으로 WorldService `/evaluate` 호출
     - 결과 active 집합을 기반으로 `/apply` 또는 `/activation` 업데이트
  2. **자본 배분 루프**
     - WorldService가 world별 활성 전략 + alpha metrics를 기반으로
       `world_allocations` + `strategy_allocations` 추천 안을 계산
     - 운영자는 이 안을 수용/수정해 `/allocations` (`upsert_allocations`)로 전송
  3. **실행**
     - 리밸런싱 계획이 실행 계층(브로커리지/오더 시스템)에 전달되어 실제 포지션이 맞춰진다.

- **문서 반영**
  - `docs/ko/world/world.md`와 `docs/ko/architecture/worldservice.md`에 “World‑Level Allocation Loop”를 하나의 섹션으로 명시하고, 완료된 radon 계획(`maintenance/radon_worldservice.md`)은 폐기.
  - CLI 문서(또는 추가할 가이드)에:
    - “전략 제출 루프(개발자)”와
    - “월드 평가/리밸런싱 루프(운영자)”를 나란히 도식화.

---

## 4. 설계 문서 재구성 가이드 (문서 단위 As‑Is / To‑Be)

### 4.1 `docs/ko/architecture/architecture.md`

- **As‑Is**
  - DAG 재사용, ComputeContext, WorldService/Gateway/DAG Manager 계층 구조와 같은 “시스템 관점” 설명이 중심이다.
  - Core Loop(사용자 관점 전략 생애주기)는 간접적으로만 드러난다.

- **To‑Be**
  - 문서의 맨 앞 또는 0. 개요에 **Core Loop 섹션**을 추가:
    - 전략 작성 → 제출 → 백테스트/replay → 평가 → 활성화/자본 배분 → 모니터링/개선
    - 각 단계 옆에 “주요 컴포넌트(Runner/Seamless/WorldService/Allocation 등)”를 짧게 표시.
  - 나머지 세부 계층 설명은 이 Core Loop 단계에 매핑되도록 재배열:
    - 예: HistoryWarmup/Seamless → “백테스트/replay 단계”
    - Policy/Activation → “평가/활성화 단계”
    - Allocation/Rebalancing → “자본 배분 단계”

### 4.2 `docs/ko/world/world.md`

- **As‑Is**
  - World 개념, Policy DSL, 2‑Phase Apply, Activation Table 등 “월드 중심 설계”를 잘 정리하고 있다.

- **To‑Be**
  - “World = 전략 생애주기 관리 단위”를 Core Loop와 바로 연결:
    - World가 맡는 책임: 정책 평가, 활성/비활성 관리, 자본 배분 계획, 리스크 게이트.
  - `/evaluate`, `/apply`, `/activation`, `/allocations` API 관계를
    - “전략 제출 루프(개발자)” vs “월드 운영 루프(운영자)” 관점으로 재정렬.

### 4.3 `./simplification_proposal.md`

- **As‑Is**
  - Runner.submit 통합, Mode 단순화, CLI v2 도입 등 v2.0 단순화 작업이 “구현 완료”로 정리되어 있다.

- **To‑Be**
  - 이 문서를 “v2.0 기반 단순화 1차 완료 보고서”로 위치시키고,
  - 본 문서의 To‑Be 항목들(auto_returns, WorldService 일원화, World Allocation Loop)을
    **후속 단순화 P1/P2 항목**으로 언급:
    - 예: “P1: auto_returns + SR 통합”, “P2: WorldService 평가/할당 일원화”.

### 4.4 Auto Returns / SR 관련 설계 문서들

- `./auto_returns_unified_design.md`  
  `./sr_integration_proposal.md`

- **As‑Is**
  - 두 문서 모두 개별 경로의 설계를 다루고 있어,
    “Core Loop 상에서 어떤 문제를 해결하는지”가 상단에서 바로 드러나지 않는다.

- **To‑Be (공통 템플릿 제안)**
  - 각 문서 상단에 다음과 같은 공통 블록을 추가:
    - `목적:` Core Loop의 어느 단계를 단순화/자동화하기 위한 설계인지 한 줄로 설명
    - `As‑Is:` 현재 구현/사용 경험에서 사용자가 겪는 문제 요약
    - `To‑Be:` 이 설계가 성공했을 때 사용자가 얻게 될 경험(전략 작성/제출/평가 관점) 요약
  - `./auto_returns_unified_design.md`의 경우:
    - 구현/체크리스트 상태를 상단에서 계속 갱신해  
      Runner 전처리/returns_source/파생 헬퍼의 정합성을 추적 가능하게 한다.

---

## 5. 이 문서의 역할

- 이 문서는 **“완전한 구현이 없는 상태에서의 완전한 문서”**를 지향한다.
  - 즉, 현재 코드/구현 상태(As‑Is)를 숨기지 않고,
  - 목표 경험(To‑Be)을 기준으로 문서 구조를 미리 정렬해 둔다.
- 구현이 따라오지 않은 기능은:
  - 각 설계 문서 상단의 As‑Is/To‑Be/Checklist에 명시하여,
  - 독자가 “이 기능은 설계만 있고 아직 구현 전”이라는 사실을 바로 알 수 있게 한다.

이 가이드를 바탕으로,

1. `architecture.md` / `world.md` / `simplification_proposal.md`에 Core Loop 중심 섹션을 추가하고,
2. auto_returns / SR 설계 문서들에 As‑Is/To‑Be 템플릿을 도입하며,
3. Runner.submit / WorldService / Allocation 경로를 하나의 “World‑First Core Loop”로 설명하는  
   상위 설계 문서를 정비하면,

사용자는 “전략 개발 및 개선 루프”에만 집중하고도  
시스템 나머지 부분이 어떤 식으로 자동으로 움직이는지 이해할 수 있게 된다.
