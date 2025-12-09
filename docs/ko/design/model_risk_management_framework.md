---
title: "QMTL 모델 리스크 관리(MRM) 프레임워크 스케치"
tags: [design, mrm, governance, validation]
author: "QMTL Team"
last_modified: 2025-12-09
status: draft
---

# QMTL 모델 리스크 관리(MRM) 프레임워크 스케치

!!! abstract "목표"
    이 문서는 QMTL에서 사용하는 **전략/월드/검증 시스템 전반에 대한 모델 리스크 관리(Model Risk Management, MRM)** 프레임워크를 개략적으로 정리한다.  
    `world_validation_architecture.md`가 WorldService 검증 계층의 기술 설계를 다룬다면, 본 문서는 **역할·책임(RACI), 거버넌스, 벤치마크/챌린저, 리포트/아티팩트** 층을 다룬다.

관련 문서:

- World 검증 계층 설계: [world_validation_architecture.md](world_validation_architecture.md)
- World 사양: [../world/world.md](../world/world.md)
- 아키텍처 개요: [../architecture/architecture.md](../architecture/architecture.md)
- WorldService 평가 런 & 메트릭 API: [worldservice_evaluation_runs_and_metrics_api.md](worldservice_evaluation_runs_and_metrics_api.md)

---

## 0. 범위 & 전제

- 범위:
  - 전략/월드 단위 모델의 **검증·승인·모니터링**에 대한 조직·프로세스 프레임워크
  - World 검증 계층(Validation Rules/Profiles/EvaluationRun)의 **“사용 규칙”과 책임 분배**
- 비범위:
  - 개별 전략 아이디어/팩터의 이론적 타당성 논의
  - 세부 코드 구현/테스트/배포 파이프라인
  - 법무·컴플라이언스 정책 자체

전제:
- 기술 설계는 `world_validation_architecture.md`를 따른다.
- 본 문서는 **“누가, 언제, 무엇을 승인/리포트/감독하는지”**를 한 페이지에 정리하는 것을 목표로 한다.

---

## 1. 역할 & 책임 (RACI 스케치)

### 1.1 주요 역할 정의

- **Model Owner / PM**
  - 전략 아이디어, 구현, 성과 책임을 가진 주체
- **Quant Research**
  - 전략 연구, 백테스트/실험, 모델링 가정 문서화 담당
- **Model Validator / Risk**
  - World 검증 프로파일/룰 설계 및 변경 승인
  - Validation Report 작성/리뷰
- **Operations / Trading**
  - 실행/운영 측면에서 모델 사용 여부·조건 확인
  - override·비상 중단 등 운영 의사결정 참여
- **Governance / Committee (선택)**
  - 고위험 모델/World에 대한 최종 승인/중단 권한

### 1.2 RACI 매트릭스 (개략)

```text
활동                                 | Owner | Quant | Risk | Ops | Gov
-------------------------------------+-------+-------+------|-----|----
전략 아이디어/팩터 설계              |  R    |  A    |  C   |  I  | I
백테스트/실험 설계                   |  C    |  A    |  C   |  I  | I
Model Card 작성/업데이트             |  A    |  R    |  C   |  I  | I
World validation 프로파일 설계/변경  |  C    |  C    |  A/R|  I  | I
World policy(YAML) 변경 리뷰/승인    |  C    |  C    |  A  |  C  | I
EvaluationRun/Validation 결과 검토   |  C    |  C    |  A  |  C  | I
Validation Report 작성/승인          |  I    |  C    |  A/R|  C  | I
paper 승격 결정                      |  A    |  C    |  C  |  C  | I
live 승격/중단 결정                  |  C    |  C    |  A  |  A  | R
override 승인                         |  C    |  C    |  A  |  A  | R
```

> R: Responsible / A: Accountable / C: Consulted / I: Informed  
> 실제 조직 구조에 따라 역할은 통합/분리될 수 있으며, 위 표는 최소 프레임워크 스케치다.

---

## 2. 모델 생애주기 & 승인 흐름

### 2.1 단계

1. **개발(Development)**  
   - 아이디어/팩터 연구, 백테스트, 구현, 코드 리뷰, 기본 품질 검사.
2. **사전 검증(Pre‑Validation)**  
   - Model Card 작성, World/validation 프로파일 후보 선택, 로컬 ValidationPipeline 실행.
3. **정식 검증(Validation)**  
   - EvaluationRun 생성, validation profiles 적용, Validation Report 초안 작성.
4. **승인(Approval)**  
   - paper 승격 승인, live 승격/보류/반려 결정.
5. **운영/모니터링(Live Monitoring)**  
   - Live EvaluationRun 정기 생성, 성과 드리프트/리스크 모니터링.
6. **리뷰/폐기(Review & Decommission)**  
   - 유효성 상실/전략 종료 시 Validation Report/히스토리 정리, world policy 정리.

### 2.2 World validation과의 연결

- Pre‑Validation/Validation 단계에서:
  - `world_validation_architecture.md`의 v1 코어 지표/룰을 적용해 go/no‑go 후보군 필터링.
- Approval 단계에서:
  - Validation Report + Model Card + risk tier를 근거로 paper/live 승격 여부 결정.
- Live Monitoring 단계에서:
  - live vs backtest 성능, validation_health, override 기록을 기반으로 자동/수동 demotion 후보를 관리.

---

## 3. 아티팩트: Model Card, Evaluation Store, Validation Report

### 3.1 Model Card (전략 정의 문서)

각 전략은 최소한 다음 정보를 포함하는 Model Card를 가져야 한다.

- ID/버전: `strategy_id`, `model_card_version`
- 목적: 타겟 시장/자산군, 투자 가설
- 데이터: 사용 데이터 소스, 빈도, 전처리, 주요 제한사항
- 모델 구조: 주요 피처/신호, 규칙/모델 타입(룰 기반, ML 등)
- 핵심 가정: 트렌드 지속성, 정규성/독립성, 유동성 가정 등
- 한계/취약성: 데이터 커버리지, 비정상 구간, 구조적 약점

Model Card는 EvaluationRun·Validation Report와 **버전 링크**를 가진다 (`model_card_version`).

### 3.2 Evaluation Store (실험/검증 추적)

`world_validation_architecture.md`에서 제안한 EvaluationRun/EvaluationMetrics/RuleResult 스키마를 기반으로:

- **Evaluation Store**는 각 `(world,strategy,run_id)`에 대한
  - 메트릭, Rule 결과, policy 버전, override 기록, 코드/데이터 snapshot id를 보관하는 저장소다.
- 이 Store는:
  - Validation Report 생성,
  - 정책 변경 전후 diff 분석,
  - “나쁜 전략” regression test,
  - 외부 리스크/감사 대응 시 근거 자료로 사용된다.

### 3.3 Validation Report (사람이 읽는 검증 요약)

Validation Report는 Evaluation Store에 저장된 정보를 사람이 읽기 좋은 형태로 요약한 문서이며, 대략 다음 구조를 갖는다.

- 0. 요약 (Summary)
- 1. 범위/목적 (Scope & Objective)
- 2. 모델 설명 (Model Card 요약)
- 3. 검증 방법 (사용한 프로파일/룰/지표, 벤치마크)
- 4. 결과 (pass/warn/fail, recommended_stage, 주요 RuleResult)
- 5. 리스크/한계 (데이터/모델/운영 측 한계)
- 6. 권고사항 (승격/보류/폐기, 추가 모니터링 조건)

Validation Report는 Risk/Validator가 작성 및 승인하며, live 승격/중단 결정의 주된 근거로 사용된다.

---

## 4. 벤치마크 & 챌린저 모델

### 4.1 벤치마크 유형

가능한 경우 각 전략/World에 대해 다음과 같은 벤치마크를 정의한다.

- 단순 Buy&Hold 또는 cap‑weighted index (동일 universe)
- naive factor 전략 (단순 모멘텀/밸류/캐리 등)
- 기존 production 전략 또는 포트폴리오

### 4.2 검증에서의 활용

- CohortRule/PortfolioRule에서:
  - 후보 전략의 성과/리스크가 벤치마크 대비 의미 있게 개선되었는지(Sharpe uplift, DD/ES 개선 등)를 확인한다.
- Validation Report에서:
  - “벤치마크 대비 어느 지점이 개선/악화되었는지”를 명시적으로 기술한다.

벤치마크 자체의 정의/선택은 World/자산군에 따라 달라질 수 있으며, 본 문서는 “벤치마크를 명시적으로 두고 비교한다”는 원칙만을 고정한다.

---

## 5. 모니터링 & 정책 안정성 지표

### 5.1 Live Monitoring 핵심 지표 (개념)

Live Monitoring은 `world_validation_architecture.md`에서 정의한 메트릭을 기반으로, 다음과 같은 지표를 중점적으로 본다.

- 최근 30/60/90일 live Sharpe/MDD/ES vs backtest 기준
- live_vs_backtest_sharpe_ratio 등 성능 decay 지표
- override 발생 빈도, 빈도 증가 추세

이 지표는:
- 자동 demotion 후보 선정,
- Validation Report 업데이트,
- World/전략 재검증 우선순위 결정에 사용된다.

### 5.2 Validation Health & Policy Stability

검증 시스템 자체의 건강 상태를 보기 위해 다음과 같은 메타 지표를 추적하는 것을 권장한다.

- validation_health.metric_coverage_ratio
- validation_health.rules_executed_ratio
- validation_health.validation_error_count
- validation_policy_age_days
- ruleset_change_count_last_90d

이 값들은 World/Stage별로 집계하여:
- 검증 계층의 미성숙 구간,
- 과도한 정책 churn,
- 지속적인 에러/누락 발생 구간을 식별하는 데 사용한다.

---

## 6. 스트리밍 Core Loop와의 정렬

QMTL의 Core Loop는 WorldService/Gateway/SDK가 ControlBus/Commit Log 스트림을 중심으로 동작한다. MRM 프레임워크도 이 스트리밍 특성을 존중해야 한다.

- EvaluationRun/Validation 결과는 **단발성 batch 결과**가 아니라,  
  “시간에 따라 축적되는 평가/모니터링 이벤트의 스냅샷”으로 취급한다.
- Runner.submit 경로에서는:
  - 필수 최소 검증만 동기적으로 수행하고,
  - 심층 검증/캠페인/Cohort/Portfolio/Stress 룰은 EvaluationRun 이벤트 스트림을 소비하는 별도 파이프라인에서 수행한다.
- WorldService는 필요 시 `EvaluationRunCreated`/`EvaluationRunUpdated`/`ValidationProfileChanged` 등의 이벤트를 발행하고,  
  검증/리포트/리스크 모듈은 이를 구독해 비동기적으로 Rule을 실행한다.
- 리스크 대시보드/검증 UI는 WS DB를 직접 때리기보다는,  
  스트림에서 만들어진 “상태 뷰”(예: Redis/캐시/머티리얼라이즈드 뷰)를 조회하는 구조를 목표로 한다.

SDK 관점에서는:

- `Runner.submit(..., world="...")` 호출 후,  
  `SubmitResult`에 포함된 `evaluation_run_id` 또는 월드/Run 링크를 사용해 WS에서 지표가 준비되었는지 조회(poll)하는 패턴을 기본으로 한다.
- **“지표가 준비되면 호출되는 콜백 헬퍼”** 같은 편의 기능은,
  - World 검증 계층 설계(`world_validation_architecture.md`)와 SDK 측 EvaluationRun 조회 플로우 설계가 정착된 이후,  
  - 스트리밍 이벤트(`EvaluationRunUpdated` 등)를 구독하는 형태로 설계·도입 여부를 논의한다.

---

## 7. SR 11‑7 관점에서의 위치

`world_validation_architecture.md` §8에서 기술 설계를 SR 11‑7 관점으로 매핑했다면, 본 문서는 그 위에 **역할/프로세스/리포트 레이어**를 덧붙인다.

- 개념적 건전성:
  - Model Card, RACI, validation_profiles 설계
- 결과 분석·벤치마킹:
  - 벤치마크/챌린저 모델 정의, Validation Report 내 비교 섹션
- 지속 모니터링:
  - Live Monitoring, Validation Health/Policy Stability 지표
- 거버넌스/독립성:
  - 독립 검증(Repo/권한 분리), override 로깅, 승인 플로우(RACI)

이 문서는 “소규모/중형 조직에서도 현실적으로 운영 가능한 MRM 최소 프레임워크”를 목표로 하며,  
필요 시 조직 규모·규제 요구에 따라 위원회 구조/리포트 포맷을 세분화해 확장할 수 있다.
