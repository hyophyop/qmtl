---
title: "World 검증 v1 구현 계획"
tags: [design, world, validation, implementation-plan]
author: "QMTL Team"
last_modified: 2025-12-09
status: draft
---

# World 검증 v1 구현 계획

!!! abstract "역할"
    이 문서는 `world_validation_architecture.md`와 `model_risk_management_framework.md`를 기반으로,  
    **v1 단계에서 실제로 구현할 범위와 순서를 작업자 관점에서 정리한 구현 계획서**다.  
    설계 문서 그 자체를 수정하기보다는, 이 계획서를 TODO/체크리스트로 사용해 “설계를 잃지 않고 큰 변경”을 수행하는 것이 목적이다.

관련 설계 문서:

- World 검증 계층 설계: [world_validation_architecture.md](world_validation_architecture.md)
- 모델 리스크 관리 프레임워크: [model_risk_management_framework.md](model_risk_management_framework.md)

---

## 1. v1 구현 스코프 요약

v1은 **“단일 전략 + 단일 World에 대한 기본 검증”**을 안정적으로 도입하는 것을 목표로 한다.  
다음 항목만 실제 구현 대상으로 포함하고, 그 외(코호트/포트폴리오/Stress/Live 프로파일 등)는 v1.5+로 남겨둔다.

### 1.1 EvaluationRun / Metrics

- EvaluationRun (WS 쪽)
  - 필수 필드: `run_id`, `world_id`, `strategy_id`, `stage`, `risk_tier`
  - validation 메타: `validation.policy_version`, `validation.ruleset_hash`, `validation.profile`, `summary.status`, `summary.recommended_stage`
- EvaluationMetrics (v1 core 필드만)
  - returns: `sharpe`, `max_drawdown`, `gain_to_pain_ratio`, `time_under_water_ratio`
  - sample: `effective_history_years`, `n_trades_total`, `n_trades_per_year`
  - risk: `adv_utilization_p95`, `participation_rate_p95` (factor_exposures 등은 v1.5+)
  - robustness: `deflated_sharpe_ratio`, `sharpe_first_half`, `sharpe_second_half`
  - diagnostics: `strategy_complexity`, `search_intensity`, `validation_health.metric_coverage_ratio`, `validation_health.rules_executed_ratio`, `returns_source`

### 1.2 Rule / DSL

- Rule 타입 (v1)
  - DataCurrencyRule, SampleRule, PerformanceRule, RiskConstraintRule
  - 단일 EvaluationRun(단일 전략)만 평가 (Cohort/Portfolio/StressRule은 v1.5+)
- RuleResult (필수 필드)
  - `status`, `severity`, `owner`, `reason_code`, `reason`, `tags`, `details`
- World policy DSL (v1)
  - `validation_profiles.backtest` / `validation_profiles.paper`의 v1 core 필드
  - `default_profile_by_stage.backtest_only/paper_only`
  - `validation.on_error=fail`, `validation.on_missing_metric=fail`
  - `live` 프로파일, portfolio 섹션은 정의만 두고 v1에서는 사용하지 않는다.

### 1.3 MRM / 아티팩트

- Model Card
  - 최소 필수 필드: ID/버전, 목적, 데이터 개요, 핵심 가정/한계
- Validation Report (초안 포맷)
  - Summary, Scope/Objective, Model 요약, 사용한 프로파일/룰/지표, 결과, 한계/권고사항
- Override 로깅
  - `override_status`, `override_reason`, `override_actor`, `override_timestamp` 필드만 구현

---

## 2. 설계 섹션 ↔ 코드 모듈 매핑

구현 중 설계를 잃지 않기 위해, 주요 문서 섹션을 예상 코드 위치와 매핑해 둔다. (실제 모듈명/경로는 구현 시점에 조정 가능)

| 설계 섹션 | 개념 | 예상 코드 위치 예시 |
|----------|------|----------------------|
| §7.1 EvaluationRun | EvaluationRun 모델/저장소 | `qmtl/services/worldservice/models/evaluation_run.py` |
| §7.2 EvaluationMetrics | 메트릭 스키마 | `qmtl/services/worldservice/schemas/evaluation_metrics.py` |
| §7.3 RuleResult | 룰 평가 결과 | `qmtl/services/worldservice/policy_engine.py` 내 새 모델 |
| §7.4 validation_profiles DSL | World policy validation 블록 | `qmtl/services/worldservice/policy_engine.py` DSL 파서 |
| §3 ValidationRule 인터페이스 | 룰 구현/adapter | `policy_engine.py` 또는 `validation_rules.py` |
| §10 품질 목표/SLO | 모니터링 지표 정의 | `docs/ko/operations/*` / alert_rules.yml 연계 |
| §12 인바리언트 | CI/E2E 체크 조건 | `tests/e2e/core_loop` / 신규 validation 테스트 |

이 표를 작업 초기에 한 번 확정해 두고, 실제 코드 경로가 바뀌면 이 문서를 함께 업데이트한다.

---

## 3. Vertical Slice 기반 단계별 계획

### 3.1 P1 — EvaluationRun 저장/조회 (스키마만)

목표:
- WorldService에 EvaluationRun 모델/저장소를 추가하고, Runner.submit에서 `run_id` 생성·조회까지 연결한다.

범위:
- `evaluation_runs` 테이블/컬렉션 추가 (필수 메타만)
- WS API에 EvaluationRun 조회 endpoint (internal 용) 추가
- Runner.submit → WS로 EvaluationRun 생성/링크 수신 (SubmitResult.evaluation_run_id)

비범위:
- Rule 평가/validation_profiles 적용은 아직 하지 않는다 (status 등은 placeholder).

### 3.2 P2 — RuleResult 도입 & 단일 전략 Rule 엔진

목표:
- 기존 policy_engine 로직을 Rule 클래스로 래핑하고, RuleResult를 생성해 EvaluationRun.validation.results에 저장한다.

범위:
- ValidationRule 인터페이스 구현
- DataCurrency/Sample/Performance/RiskConstraint 룰을 Rule 클래스로 포장
- RuleResult 스키마 도입
- EvaluationRun.validation.results에 RuleResult 맵 저장

비범위:
- Cohort/Portfolio/StressRule, live_monitoring, 캠페인 수준 평가는 포함하지 않는다.

### 3.3 P3 — validation_profiles DSL(v1) 적용

목표:
- World policy에 `validation_profiles.backtest/paper` 블록을 추가하고, v1 core 필드만 적용한다.

범위:
- DSL 파서 확장 (기존 thresholds를 selection으로 alias 처리)
- 몇 개 샘플 World YAML을 새 DSL로 마이그레이션
- v1 validation_profile에 따라 어떤 Rule이 어떤 파라미터로 구성되는지 결정

비범위:
- 전체 World 파일 일괄 변환, live 프로파일, portfolio 섹션 적용은 v1.5+.

### 3.4 P4 — Validation Report/아티팩트 최소 구현

목표:
- EvaluationRun + Model Card 정보를 바탕으로 기계 생성 가능한 Validation Report 초안을 만들 수 있게 한다.

범위:
- Report 생성 헬퍼/스크립트 (예: `scripts/generate_validation_report.py`)
- 최소 Summary/Scope/Result/Key Rules 섹션만 포함

비범위:
- 리치 포맷팅, UI 통합, 자동 배포는 v1.5+.

---

## 4. 설계 변경 시 문서 업데이트 규칙

구현 중 설계 일부를 바꾸고 싶어질 때는, 코드부터 바꾸지 말고 다음 순서를 따른다.

1. 해당 설계 문서 섹션 옆에 짧은 note를 추가한다.
   - 예: `!!! note "v1 구현 예정 변경"` 형태로 “여기서 말하는 X는 v1에서는 Y로 단순화된다” 식으로 주석.
2. 이 구현 계획 문서에 “영향 받는 섹션 ↔ 코드 모듈”을 한 줄 메모한다.
3. 코드 변경 후, 다시 설계 문서를 훑으며 거짓이 된 문장을 수정하거나 “v1.5+ 예정”으로 명시한다.

이 규칙을 통해 “문서가 오래된 설계 스냅샷으로 남는 것”을 방지한다.

---

## 5. 체크리스트 (v1 완료 기준)

v1 구현이 완료되었다고 주장하기 위한 최소 체크리스트:

- [ ] WS에 EvaluationRun 모델/저장소가 추가되었고, Runner.submit 결과로 run_id를 확인할 수 있다.
- [ ] EvaluationMetrics v1 core 필드가 채워지고, WorldService에서 이를 조회할 수 있다.
- [ ] DataCurrency/Sample/Performance/RiskConstraint Rule이 RuleResult를 반환하며, EvaluationRun.validation.results에 저장된다.
- [ ] World policy에 validation_profiles.backtest/paper 블록이 존재하고, v1 core 필드만으로도 go/no‑go 판단을 할 수 있다.
- [ ] 최소 한 개 World/전략에 대해 Validation Report 초안을 자동 생성할 수 있다.
- [ ] §12의 인바리언트(특히 Invariant 1/2/3)에 대한 테스트/체크가 CI 또는 e2e 테스트로 구현되었다.

이 체크리스트를 모두 만족한 시점을 v1 “검증 계층 구현 완료”로 간주하고, 이후 Cohort/Portfolio/StressRule, live 프로파일, 포트폴리오 리스크, capacity, advanced robustness 지표 등 v1.5+ 범위를 별도 계획으로 확장해 나간다.

