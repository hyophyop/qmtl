---
title: "Core Loop × WorldService 단계별 고도화 로드맵"
tags: [design, roadmap, core-loop, worldservice]
author: "QMTL Team"
last_modified: 2025-12-08
status: draft
---

# Core Loop × WorldService 단계별 고도화 로드맵

이 문서는 Core Loop를 **“전략+월드만 제출하면, 월드가 모드·단계·캠페인을 관리하는 구조”**로 수렴시키기 위한 **실행 로드맵**이다.  
아키텍처 문서(`architecture/architecture.md`)가 전체 그림을 잡는다면, 이 문서는 **구현 작업자가 “지금 무엇을, 어떤 순서로 바꾸는지”를 잃지 않게 해 주는 북극성 가이드** 역할을 한다.

핵심 목표는 다음 한 줄로 요약된다.

> **사용자는 전략 로직과 월드만 지정하고, “backtest → 검증 → paper → (선택적) live” 단계는 월드 정책과 WorldService가 관리한다.**

여기서 제안하는 단계들은 **강한 순서 제약**이 있다. 가능한 한 아래 순서대로 적용해야 한다.

- Phase 0–1: **계약 정리·WS‑우선 모드 결정** (기존 기능 강화, 행동 변화 최소)
- Phase 2–3: **Evaluation Run 1급 개념화, world‑first 제출 UX** (API/모델 변화)
- Phase 4–5: **캠페인 오케스트레이션, 검증 단계 고도화** (전략 생애주기 자동화 수준 확대)

## 0. 사전 합의: 지향점과 비범위

### 0.1 지향점

- 모드는 **사용자가 직접 선택하는 플래그**가 아니라,  
  **월드 정책과 WorldService가 결정하는 상태**에 가깝게 재정의한다.
- Core Loop의 표면은 다음 흐름을 기준으로 설계한다.

```text
전략 작성 → Runner.submit(strategy, world)
          → (월드 안에서 backtest/검증/승격 후보 선정)
          → paper/live 후보군 관리
          → 운영자가 live 적용 여부를 결정
```

- 소규모 조직에서도 **기술로 리스크를 통제**할 수 있도록,  
  **월드의 “검증” 단계를 고도화**하고, live 승격은 기본적으로 **명시적인 apply/운영자 승인**을 요구하는 방향을 기본값으로 한다.

### 0.2 비범위

- WorldService 안에 **대규모 백테스트 엔진을 새로 만들지 않는다.**
  - 히스토리 replay, returns/지표 계산은 기존대로 Runner/SDK/`ValidationPipeline`이 담당한다.
  - WS는 **이미 계산된 metrics/PnL·지표를 받아 정책을 적용하고, 결과/스냅샷/상태를 관리**하는 역할에 집중한다.
- Core Loop 변경과 무관한 인프라 리팩터링(브로커 교체, DAG 모델 재설계 등)은 이 로드맵 범위에서 다루지 않는다.

---

## Phase 0 — 목표 형상·계약 정리 (문서 중심)

**목표:** 구현에 앞서 “어디로 가는지”에 대한 서술을 명확히 하고, 기존 문서와 충돌이 없도록 한다.

### 해야 할 일

- `architecture/architecture.md`·`world/world.md`·`design/worldservice_evaluation_runs_and_metrics_api.md`를 기준으로 다음을 문장으로 고정한다.
  - **WS SSOT 원칙:** 실행 모드/단계의 단일 진실 소스는 항상 WorldService의 `effective_mode`/정책 결과다.
  - Runner/SDK는 `mode`를 선택하더라도, **WS 결정이 존재하는 한 항상 이를 우선한다.**
  - “모드는 선택값, WS `effective_mode` + world 정책은 계약”이라는 관점을 문서에서 일관되게 강조한다.
- World 정책 DSL에서 이미 존재하는 필드들(`data_currency`, `selection.gates`, `hysteresis` 등)을  
  “Core Loop 단계별 결정에 사용되는 1급 개념”으로 명시한다.

### 산출물

- 업데이트된 설계 문서:
  - WS SSOT·safe_mode·강등 규칙이 명확히 서술된 `architecture/architecture.md`/`world/world.md`
  - Evaluation Run 개념이 설명된 `design/worldservice_evaluation_runs_and_metrics_api.md`
- 이 로드맵 문서(`design/core_loop_world_roadmap.md`)를 **작업자용 참조**로 링크.

---

## Phase 1 — WS‑우선 모드 결정 계약 강화

**목표:** 현재 v2 구현이 이미 가진 “WS 결정 우선, 기본은 compute‑only(backtest)” 행동을 **계약 수준으로 못 박고, 코드·테스트에 반영**한다.

### 해야 할 일

1. **모드 결정 흐름 정리**
   - `qmtl.runtime.sdk.mode.Mode` / `mode_to_execution_domain` / `execution_domain_to_mode` / `effective_mode_to_mode` 사용처를 점검한다.
   - `qmtl.runtime.sdk.execution_context.resolve_execution_context`와  
     `qmtl.runtime.helpers.runtime.determine_execution_mode`가  
     아래 순서를 따르도록 확인·보완한다.
     1. explicit `mode` 인자
     2. 기존 `execution_mode` 컨텍스트
     3. WS `effective_mode`에서 온 domain 힌트
     4. 그 외에는 `backtest` (safe default)

2. **WS 결정 우선 적용**
   - Gateway/SDK가 WS `DecisionEnvelope` / `ActivationEnvelope`를 수신할 때:
     - `effective_mode`를 로컬 `compute_context` 및 `SubmitResult.ws.*`에 저장한다.
     - Runner/SDK가 자체적으로 execution_domain을 “승격”하지 않도록 보장한다.

3. **강등(safe_mode)·compute‑only 계약**
   - WS 결정이 없거나 stale일 때,  
     또는 `as_of`/`dataset_fingerprint`가 요구 조건을 만족하지 않을 때:
     - 항상 `execution_domain = backtest`, 주문 게이트 OFF, `safe_mode=True`, `downgraded=True`로 수렴하도록 한다.
   - 이 동작을 Core Loop 계약 테스트(`tests/e2e/core_loop`)와  
     별도 유닛 테스트에서 검증한다.

### 산출물

- 코드:
  - `runtime/sdk/execution_context.py`, `runtime/helpers/runtime.py`, `runtime/sdk/submit.py`의 모드·도메인 결정 경로가 WS‑우선 규칙을 따른다.
- 테스트:
  - WS 결정 부재/만료/에러 시 compute‑only로 강등되는 시나리오.
  - WS `effective_mode=validate/compute-only/paper/live`에 따라 SDK가 도메인을 어떻게 설정하는지 검증.

---

## Phase 2 — Evaluation Run을 1급 개념으로 올리기

**목표:** “이 제출이 지금 월드 내에서 어떤 단계인지”를 월드·WS 관점에서 추적할 수 있도록, Evaluation Run 모델을 실제 도입한다.

### 해야 할 일

1. **모델 정의**
   - `design/worldservice_evaluation_runs_and_metrics_api.md`의 정의를 기반으로,  
     WorldService 내부에 다음 스키마를 도입한다.
     - 키: `(world_id, strategy_id, evaluation_run_id)`
     - 상태: `submitted / backtest_running / evaluating / evaluated / activated / rejected / expired`
     - 메타: 생성/갱신 시간, 사용된 데이터 윈도우, 사용된 정책 버전 등.

2. **Runner.submit ↔ Evaluation Run 연동**
   - Runner.submit 호출 시:
     - WS/Gateway가 **평가 런을 생성**하거나 이미 존재하는 런을 갱신한다.
     - `SubmitResult`에 적어도 다음 중 하나를 포함한다.
       - `evaluation_run_id`
       - `evaluation_run_url` (상태/메트릭 조회용 링크)
   - 초기 단계에서는 여전히 “동기 파이프라인”으로 돌아도 괜찮지만,  
     **결과가 어디에 기록되는지**가 Evaluation Run으로 명확히 남아야 한다.

3. **상태 전이 구현**
   - Runner/SDK가 backtest/Validation/WS Evaluate를 수행하는 동안:
     - 적절한 시점에 `backtest_running` / `evaluating` / `evaluated` 등으로 상태를 업데이트한다.
   - `/worlds/{world}/strategies/{strategy}/runs/{run_id}` 형태의 상태 조회 API를 시범 구현한다.

### 산출물

- WS 코드:
  - Evaluation Run 저장소/모델 + 상태 전이 로직.
- API:
  - 평가 런 상태 조회 endpoint (초기에는 internal/admin 용도여도 괜찮다).
- Runner/SDK:
  - `SubmitResult`에 evaluation run 식별자를 포함.

---

## Phase 3 — world‑first 제출 UX & mode 인자 축소

**목표:** 실사용 DX를 “전략 + 월드” 중심으로 재정렬하고, `mode`는 점차 hint/고급 옵션으로 밀어낸다.

### 해야 할 일

1. **API 서피스 정리**
   - Python:
     - `Runner.submit(MyStrategy, world="...")`를 문서/예제에서 **기본 추천 경로**로 만든다.
     - `mode=` 인자는 여전히 허용하되, docstring/가이드에서 “advanced/실험용”으로 명시한다.
   - CLI:
     - `qmtl submit strategy.py --world my-world`를 권장 기본 형식으로 문서화한다.
     - `--mode` 플래그는 고급 옵션 섹션으로 이동한다.

2. **mode=None 코드 경로 지원**

   - 내부적으로 `mode=None`을 허용하고, 이 경우:
     - 실행 도메인 선택은 **WS `effective_mode` + world/data 정책**에 따라 결정된다.
     - Runner/SDK는 compute‑only 강등·게이트 설정만 담당한다.

3. **리그레이션 방지**

   - 기존 `mode=Mode.BACKTEST/PAPER/LIVE` 호출은 계속 동작하되,
     - WS가 붙어 있을 때는 `effective_mode`가 항상 최종 권위가 됨을 테스트로 보장한다.

### 산출물

- 문서:
  - Getting Started/Guides/Architecture 문서에서 “mode 없는 submit”을 기본 흐름으로 예시.
- 코드:
  - `mode=None` 경로 지원 및 테스트.

---

## Phase 4 — backtest/paper/live 캠페인 오케스트레이션

**목표:** World 정책과 Evaluation Run을 이용해 “backtest 캠페인 → paper 캠페인 → (선택적) live 캠페인”을 자동·반복적으로 관리할 수 있는 기반을 만든다.

### 해야 할 일

1. **정책 DSL에 캠페인 윈도우 도입**
   - `world/world.md`의 정책 예시에 다음과 같은 필드를 추가·정의한다 (이름은 조정 가능).
     - `campaign.backtest.window`: 최소 backtest 관찰 기간 (예: `180d`)
     - `campaign.paper.window`: 최소 paper 관찰 기간
     - `campaign.common.min_trades_per_window`, `min_sample_days` 등
   - 각 필드는 “해당 단계에서 최소로 관찰되어야 하는 PnL/지표 윈도우”로 설명한다.

2. **캠페인 상태 모델**

   - WorldService에서 Evaluation Run 집계 결과를 기반으로, 월드/전략 조합에 대해 다음과 같은 상태를 유지한다.
     - `phase: backtest_campaign | paper_campaign | live_campaign`
     - 각 phase에 대해:
       - 관찰 시작/종료 시점
       - 관찰된 sample_days, trades, sharpe, max_dd, drawdown episode 등 핵심 지표
       - “승격 가능/불가능” 플래그 및 이유

3. **스케줄링 전략**

   - 초기 단계에서는 **외부 스케줄러/워크플로**를 전제로 단순하게 시작한다.
     - 예: “매일 1회 `/worlds/{id}/evaluate` 호출 → 정책 기반 승격 후보 계산 → `/apply`로 반영 또는 큐에 보관”.
   - 이후 필요 시 WorldService 내부에 간단한 주기 평가 루프를 추가할 수 있다.

4. **Runner/CLI와의 연결**

   - Runner.submit은 여전히 “단일 호출”이지만,  
     - `SubmitResult` 또는 별도 CLI 명령어에서 “현재 캠페인 phase/윈도우/승격 조건”을 조회할 수 있게 한다.

### 산출물

- 정책:
  - 캠페인 윈도우·조건이 들어간 world policy 예제.
- WS:
  - 캠페인 상태 집계·조회 API (phase, 진행률, 승격 가능 여부).
- CLI:
  - `qmtl world status` 등에서 캠페인 phase와 핵심 지표를 요약해서 보여주는 명령.

---

## Phase 5 — 검증 단계 고도화 & live 승격 거버넌스

**목표:** 소규모 조직에서도 “기술로 리스크를 통제”할 수 있을 만큼 강한 검증 단계를 만들고, live 승격은 기본적으로 운영/거버넌스 단계에 남겨 둔다.

### 해야 할 일

1. **월드 검증 단계 고도화**

   - World 정책 DSL에서 **검증 전용 필드**를 명시적으로 구분한다.
     - 예: `validation:` 블록 아래에
       - 데이터 통화성(데이터 랙, missing coverage 비율)
       - 샘플 충분성(`sample_days`, `trades_60d`, `notional_turnover`)
       - 리스크 컷(`max_dd_Xd`, `ulcer_index`, tail risk proxy)
       - 시나리오/스트레스 테스트 결과 플래그
   - 이 블록은 “**live 후보군에 오르기 위한 최소 조건**”을 정의하는 곳으로 문서화한다.

2. **live 승격 거버넌스 옵션**

   - 정책/월드 설정에 다음과 같은 옵션을 추가한다.
     - `live_auto_apply: false` (기본값)
     - `live_requires_manual_approval: true`
   - 이렇게 하면:
     - 시스템은 **backtest/paper 캠페인까지 자동으로 후보를 추려 주고**,  
     - live 전환은 항상 `/apply` 또는 별도 “승인 플로우”를 통해서만 일어난다.

3. **운영자 친화적 리포트**

   - Evaluation Run / 캠페인 상태 / 검증 결과를 바탕으로, 운영자·리스크 담당자가 이해하기 쉬운 리포트를 설계한다.
     - 예: “최근 180일 Sharpe ≥ 0.8, max_dd ≤ 20%, 거래일 ≥ 60일을 충족하여 live 후보입니다.  
       다만 상관/섹터 제약 관점에서 A/B 전략과 다소 중복이 있으니 확인이 필요합니다.”
   - CLI/웹 UI/로그 링크 등 어떤 채널에서 이 정보를 볼지까지 포함해 설계한다.

### 산출물

- 정책:
  - 검증 단계 고도화가 반영된 world policy 예시 (`validation` 블록, 검증 지표·임계값).
- WS/도구:
  - live 승격 후보군 목록, 승격 사유/거부 사유를 요약하는 API/CLI/리포트.

---

## 6. 이 문서를 사용하는 방법 (작업자용 TL;DR)

1. **지금 내가 만지는 코드가 어느 Phase에 속하는지 먼저 정한다.**
   - 모드 결정/compute‑only 강등 로직을 건드린다면 → Phase 1.
   - Evaluation Run 모델/WS API를 바꾼다면 → Phase 2.
   - World 정책 DSL·캠페인 윈도우를 손본다면 → Phase 4–5.

2. **해당 Phase 섹션의 “해야 할 일/산출물” 체크리스트를 그대로 TODO로 사용한다.**
   - 새 기능을 추가할 때는 “이 로드맵의 어느 단계에 속하는지”를 PR/이슈 설명에 명시한다.

3. **Phase를 건너뛰지 않는다.**
   - 예를 들어 Evaluation Run을 제대로 도입하지 않은 상태에서 캠페인 오케스트레이션을 구현하면,
     - 디버깅이 어렵고, WS/Runner 간 책임 경계가 모호해지기 좋다.

4. **live 자동 승격은 항상 마지막에, 그리고 기본은 off.**
   - 이 문서는 **소규모 조직이 기술로 리스크를 제어할 수 있는 기반**을 제공하려는 것이지,
     - “사람 손을 완전히 떼는 live 자동화”를 지향하지 않는다.
   - live 자동 승격이 필요하더라도, 충분한 기간의 검증/캠페인·모니터링이 갖춰진 뒤,  
     제한된 환경에서만 opt‑in 하도록 계획한다.

이 로드맵 하나만으로도 “Core Loop를 월드 중심으로 고도화한다”는 목적과 방향성을 잃지 않고, 각 단계에서 해야 할 일을 판단할 수 있어야 한다. 세부 API·스키마는 관련 설계 문서(`architecture/*.md`, `world/*.md`, `design/worldservice_evaluation_runs_and_metrics_api.md`)를 함께 참고하되, **“지금 이 변경이 전체 그림에서 어느 Phase인지”**는 항상 이 문서를 기준으로 정한다.

