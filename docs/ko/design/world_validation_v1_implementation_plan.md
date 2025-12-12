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

## 진행 현황 (작업 체크인용)

| Phase | 범위 | 상태 | 코드 레퍼런스 / 테스트 |
|-------|------|------|------------------------|
| P1 | EvaluationRun 저장/조회 + v1 core Metrics 블록 | 완료 | `qmtl/services/worldservice/storage/*evaluation*`, `tests/qmtl/services/worldservice/test_worldservice_api.py::test_evaluation_run_creation_and_fetch` |
| P2 | RuleResult 스키마 + Rule 래핑 | 완료 | `qmtl/services/worldservice/policy_engine.py`, `tests/qmtl/services/worldservice/test_policy_engine.py` |
| P3 | validation_profiles DSL(v1) 적용 | 완료 (backtest/paper 프로파일 + severity/owner override 반영) | `policy_engine._materialize_policy`, `tests/qmtl/services/worldservice/test_policy_engine.py::{test_validation_profiles_switch_by_stage,test_validation_profile_overrides_severity_and_owner}` |
| P4 | EvaluationRun에 policy_version / ruleset_hash / recommended_stage 기록 | 완료 | `decision.py`·`services.py` 메타 전파, `policy_engine.recommended_stage`, `tests/qmtl/services/worldservice/test_worldservice_api.py::test_evaluation_run_creation_and_fetch` |
| P5 | Cohort/Portfolio/StressRule, live_monitoring | 완료 (extended_layers + append-only history + live/stress/portfolio 지표 파이프라인 + risk_hub 스냅샷 기반 베이스라인 + ControlBus consumer/모니터링 스크립트) | `policy_engine` P5 evaluators + `evaluate_extended_layers`, `worldservice.services._apply_extended_validation`, `extended_validation_worker.py`, `validation_metrics.py`, `risk_hub.py`/`routers/risk_hub.py`/`controlbus_consumer.py`, 리포트(`scripts/generate_validation_report.py`), 모니터/워커(`scripts/risk_hub_monitor.py`,`scripts/risk_hub_worker.py`), `tests/qmtl/services/worldservice/test_policy_engine.py::{test_parse_policy_with_p5_sections,test_stub_cohort_portfolio_stress_and_live_monitoring,test_evaluate_extended_layers_over_runs}`, `tests/qmtl/services/worldservice/{test_extended_validation_worker.py,test_extended_validation_worker_cov_ref.py,test_live_metrics.py,test_stress_metrics.py,test_risk_hub_validations.py,test_controlbus_consumer.py}`, `tests/qmtl/services/gateway/{test_risk_hub_publish.py,test_risk_snapshot_publisher.py}`, `tests/scripts/test_generate_validation_report.py` |

테스트 커버리지 메모:
- 정책/룰 메타데이터: `uv run -m pytest tests/qmtl/services/worldservice/test_policy_engine.py tests/qmtl/services/worldservice/test_worldservice_api.py::test_evaluation_run_creation_and_fetch`
- 추가로 전체 WS/GW 스모크/통합은 실행 시 여기에 기록

## 다음 단계 제안 (v1.5+ 하드닝)

- 이벤트/운영: ControlBus/큐 기반 risk snapshot 이벤트를 WS 워커로 트리거하는 운영 배포(현재 워커/모니터 스크립트 제공, 운영 큐 연결은 환경별 설정 필요).
- 리스크 허브 운영: gateway 전면 생산자 전환(체결/포지션 싱크 포함), blob-store ref 포맷(S3/Redis) 표준 확정, Alertmanager 룰/런북 지속 개선.
- 회귀/성능: policy diff 시뮬레이터를 “나쁜 전략” 세트와 함께 CI나 배치로 돌리는 옵션 도입, extended validation 워커 부하/성능 테스트 추가.
- SDK/문서: SDK 예제·CLI 도움말에 cohort/portfolio/stress/live 결과 조회 안내를 추가하고, 운영자용 health 체크 스크립트(`risk_signal_hub_runbook.md`)와 연결.

### 새 TODO (v1.5+)
- risk snapshot 이벤트를 ControlBus/Celery/Arq 등 운영 큐에 연결해 `ExtendedValidationWorker`/라이브·스트레스 워커가 idempotent하게 실행되도록 환경별 헬름/서비스 스크립트 추가.
- blob-store ref(s3/redis/file) 스키마와 TTL/해시/ACL 규칙을 운영 문서와 CI에 반영하고, 대용량 공분산/리턴 업로드 헬퍼를 배포.
- policy diff / “나쁜 전략” 회귀 세트를 주기 배치로 돌려 정책 변경 영향 보고서를 생성하는 스크립트(scripts/policy_diff.py 기반) 확대 적용.

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

- [x] WS에 EvaluationRun 모델/저장소가 추가되었고, Runner.submit 결과로 run_id를 확인할 수 있다.
- [x] EvaluationMetrics v1 core 필드가 채워지고, WorldService에서 이를 조회할 수 있다.
- [x] DataCurrency/Sample/Performance/RiskConstraint Rule이 RuleResult를 반환하며, EvaluationRun.validation.results에 저장된다.
- [x] World policy에 validation_profiles.backtest/paper 블록이 존재하고, v1 core 필드만으로도 go/no‑go 판단을 할 수 있다.
- [x] 최소 한 개 World/전략에 대해 Validation Report 초안을 자동 생성할 수 있다.
- [x] §12의 인바리언트(특히 Invariant 1/2/3)에 대한 테스트/체크가 CI 또는 e2e 테스트로 구현되었다.

이 체크리스트를 모두 만족한 시점을 v1 “검증 계층 구현 완료”로 간주하고, 이후 Cohort/Portfolio/StressRule, live 프로파일, 포트폴리오 리스크, capacity, advanced robustness 지표 등 v1.5+ 범위를 별도 계획으로 확장해 나간다.

---

## 6. Risk Signal Hub (exit 엔진/리스크 신호 허브) 설계 추가

`risk_signal_hub`은 실행/배분(gateway)과 검증/exit(WS, exit engine) 사이에서 **포트폴리오 스냅샷·리스크 지표·추가 exit 신호**를 SSOT로 제공하는 모듈이다. 목표는 “실행”과 “검증/리스크 신호”를 느슨하게 결합시키고, exit 엔진 같은 신규 소비자가 SDK/WS를 건드리지 않고 붙을 수 있게 하는 것.

### 6.1 역할/데이터 스코프
- 입력(생산자): gateway/alloc(실제 가중치/포지션), 리스크 엔진(공분산/상관, 스트레스 결과), 실현 리턴 파이프라인.
- 출력(소비자): WS(Var/ES/샤프 베이스라인, live 모니터링), exit engine(추가 exit 신호 판단), 모니터링 대시보드.
- 보관 데이터(예시 스냅샷 스키마):
  ```json
  {
    "as_of": "2025-01-15T00:00:00Z",
    "weights": {"strat_a": 0.35, "strat_b": 0.25, "strat_c": 0.40},
    "covariance_ref": "cov/2025-01-15",
    "covariance": {"strat_a,strat_b": 0.12, "strat_b,strat_c": 0.15},
    "realized_returns_ref": "s3://.../realized/2025-01-15.parquet",
    "stress": {"crash": {"dd_max": 0.3, "es_99": 0.25}},
    "constraints": {"max_leverage": 3.0, "adv_util_p95": 0.25},
    "provenance": {"source": "gateway", "cov_version": "v42"}
  }
  ```

### 6.2 인터페이스/배포 형태
- **이벤트**: `PortfolioSnapshotUpdated`, `CovarianceUpdated`, `RealizedReturnsIngested`, `ExitSignalEmitted` 등을 ControlBus/Kafka로 발행. WS/exit engine은 구독자로 동작.
- **조회 뷰**: KV/DB/캐시(머티리얼라이즈드 뷰)에서 `get_snapshot(world_id, as_of/version)` 형태로 읽기 전용 제공. 큰 덩어리는 ref/id만 전달하고 원본은 저장소에 둔다.
- **접근 제어**: 쓰기 주체는 gateway/리스크 엔진으로 한정, 읽기는 WS/exit engine/모니터링. 모든 업데이트에 version/hash/audit 로그를 남긴다.

### 6.3 소비자 통합 포인트
- WS: ExtendedValidationWorker가 스냅샷을 읽어 Var/ES/Sharpe 베이스라인, 포트폴리오 제약 위반 여부를 계산.
- Exit engine: 동일 스냅샷 + market/risk 지표를 사용해 전략 exit 신호를 생성하고, `ExitSignalEmitted`로 발행.
- SDK: 변경 없음. WS/exit 엔진이 hub를 통해 필요한 데이터만 읽는다.

### 6.4 운영/품질 가드
- SLA: 스냅샷 `as_of` 지연 한도(예: 5m), 실패 시 fallback(이전 버전 + 보수적 상관/σ).
- 데이터 계약: 필수 필드(weights, as_of), 선택 필드(covariance, realized_returns_ref, stress) 명시. 결측 시 정책(보수 상관=0.5 등) 정의.
- 보안: 리스크/포지션 스냅샷은 별도 권한 도메인, 감사 필수.

### 6.5 단계별 적용
1. Minimal: gateway가 스냅샷을 KV/DB에 기록, WS/exit 엔진이 조회만 수행.
2. 이벤트화: ControlBus/Kafka 이벤트 발행 + 구독 워커로 자동 갱신/트리거.
3. 확장: 공분산/스트레스 엔진 결과를 ref/id로 결합, exit 신호 발행까지 동일 허브로 관리.

### 6.6 기존/향후 작업에 대한 허브 연계 리워크
- 포트폴리오 Var/ES 계산: ExtendedValidationWorker가 gateway에서 직접 받아오던 가중치·상관/공분산을 `risk_signal_hub`의 스냅샷 조회로 대체한다. 스냅샷에 weights, covariance_ref/행렬을 포함하도록 계약을 정의한 뒤, WS는 hub에서 최신 버전만 읽는다.
- 스트레스/라이브 재시뮬레이션 워커: hub가 발행하는 `PortfolioSnapshotUpdated`/`RealizedReturnsIngested` 이벤트를 트리거로 삼아 ControlBus/백그라운드 워커에서 실행하도록 스케줄링 훅을 연결한다.
- extended_validation_scheduler: 현재 asyncio fire-and-forget 훅을 운영 큐(Celery/Arq 등)나 ControlBus 이벤트 핸들러로 교체해, hub 이벤트 → 큐 → WS 워커 실행 흐름을 구성한다.
- CI/운영 체크리스트 업데이트: hub 계약(필수 필드, as_of/버전, TTL) 준수 여부와 fail-closed 정책을 고위험 world에서 강제하는 항목을 추가한다.
- Exit Engine 연계: exit 신호는 `risk_signal_hub` 이벤트를 기반으로 생성해 ControlBus/Kafka로 발행하되, 적용 우선순위/override 정책은 별도 운영 문서에서 정의한다(초안은 [exit_engine_overview.md](exit_engine_overview.md) 참조).
- Dev/Prod 템플릿 연결: dev에서는 in-memory/SQLite에 메타를 두고 캐시/오프로드는 fakeredis 또는 순수 인메모리만 사용하며(파일/S3 영속 스토리지는 dev에서 비활성), prod에서는 Postgres+Redis 캐시+오브젝트 스토리지(S3/OBS/GCS)+Kafka/ControlBus 조합으로 hub를 운영한다. WS/exit 엔진은 동일 API/이벤트 인터페이스를 사용해 환경 차이를 흡수한다.
  - `qmtl.yml` `risk_hub` 블록을 통해 WS 라우터 토큰/inline offload 기준/BlobStore(file|redis|s3)와 gateway 생산자 클라이언트를 함께 구성해 dev↔prod 전환 시 설정 드리프트를 방지한다(단, dev 프로파일에서는 blob_store 영속형을 사용하지 않는다).
- 단계별 작업 흐름 고정:
  1) **Hub 최소 구현**: 스냅샷 저장/조회 API + `PortfolioSnapshotUpdated` 이벤트 발행.
  2) **Gateway 생산자 전환**: 리밸런스/체결 이후 hub에 weights+covariance_ref/행렬+as_of 기록(WS 직접 의존 제거).
  3) **WS 소비자 전환**: ExtendedValidationWorker/라이브·스트레스 워커가 hub 조회/이벤트 구독 기반으로 Var/ES·live/stress 계산.
  4) **Exit/모니터링 확장**: exit 엔진·대시보드가 hub 이벤트만 구독해 신호/뷰 생성, WS/SDK 변경 없이 확장.
  - 현재 구현 상태: WS는 `risk_hub` 라우터+`ExtendedValidationWorker`에 hub 조회를 연결했고, dev(인메모리/SQLite)·prod(Postgres/Redis) 환경에서 `risk_snapshots` 테이블을 통해 스냅샷을 영속화하도록 바인딩했다. 이벤트 발행/큐 연동과 gateway 생산자 전환은 후속 단계로 남겨둔다.
  - 보완 계획(요약): ControlBus/큐 구독 워커로 스냅샷 이벤트를 받아 ExtendedValidation/스트레스/라이브 워커를 idempotent 실행; gateway는 리밸런스·체결·포지션 싱크 시 스냅샷 push + ControlBus 재시도/ACL; 스냅샷 스키마에 ref/hash/TTL/idempotency 규칙을 추가하고 Redis 캐시·모니터링/알람(runbook)·e2e/부하 테스트까지 포함해 운영 완성도를 높인다.
  - 운영 가시성: risk hub freshness/누락 메트릭(`risk_hub_snapshot_lag_seconds`, `risk_hub_snapshot_missing_total`)과 Alertmanager 룰 추가, 런북/헬스 스크립트(`risk_signal_hub_runbook.md`, `scripts/risk_hub_monitor.py`) 정리, ControlBus 워커 예시(`scripts/risk_hub_worker.py`) 제공.
