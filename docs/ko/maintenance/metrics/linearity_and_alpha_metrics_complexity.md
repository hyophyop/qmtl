# 선형성·알파 메트릭 복잡도 개선 계획

## 배경 및 목표

- 이 문서는 이슈 `#1552`에서 제안된 메트릭·통계 계산 루틴 복잡도 개선 작업의 설계 요약을 다룹니다.
- radon 기준 C급 복잡도였던 대표 함수들을 대상으로 공통 계산 플로우(데이터 준비 → 계산 → 집계)를 템플릿/전략으로 분리해 이해·테스트·재사용성을 높이는 것을 목표로 합니다.
- 주요 대상:
  - `qmtl/runtime/transforms/linearity_metrics.py: equity_linearity_metrics_v2`
  - `qmtl/runtime/helpers/runtime.py: compute_alpha_performance_summary`
  - `qmtl/services/worldservice/decision.py: augment_metrics_with_linearity`

## 공통 설계 원칙

- **Template Method 패턴**
  - 복잡한 메트릭 계산을 다음 단계로 나눕니다.
    - 입력 정규화/데이터 준비
    - 핵심 통계량 계산(기울기, R², 드로다운 등)
    - 결과 집계/스코어링
  - 상위 함수는 흐름만 고정하고, 세부 계산은 헬퍼/전략에 위임합니다.

- **Strategy 패턴**
  - 메트릭/시나리오별 계산 방식을 전략 객체로 분리합니다.
  - 서비스 계층에서는 전략을 선택·조합하는 역할만 담당하고, 개별 수식/통계 구현에 직접 의존하지 않도록 합니다.

- **통계 헬퍼 모듈 재사용**
  - OLS, t-통계, 변동성/드로다운, 요약 통계 등을 작은 헬퍼 함수로 분리해 여러 모듈에서 재사용합니다.
  - 각 헬퍼는 순수 함수(pure function)에 가깝게 유지해 단위 테스트와 리팩터링을 용이하게 합니다.

## equity_linearity_metrics_v2 리팩터링

### 기존 문제

- 단일 함수 안에서 다음 요소가 섞여 있어 CC가 C(19)까지 상승했습니다.
  - 방향 처리(상승/하락)와 로그 변환 적용 여부
  - OLS 회귀와 t-통계 계산
  - TVR, 시간·신고점 기반 persistence, 드로다운 정규화
  - 위 요소를 조합한 최종 score 산출

### 개선된 구조

- 입력 정규화
  - `_prepare_oriented_series`  
    - `orientation`(up/down)과 `use_log` 옵션에 따라 `pnl` 시계열을 정규화합니다.
    - 로그 변환이 불가능한 경우(음수/0 포함)에는 원본 스페이스를 유지합니다.

- 통계 컴포넌트
  - `_trend_components`  
    - `_ols_slope_r2_t`를 통해 `(slope, r2, t_stat)`을 구하고, 양의 기울기만 `r2_up`으로 인정합니다.
    - `_spearman_rho`로 순위 상관을 측정하고, `t_slope_sig`를 별도 컴포넌트로 제공합니다.
  - `_tvr_multi_scale`  
    - `_coarse`로 여러 스케일(`scales=(1, 5, 20)` 등)에서 시계열을 다운샘플링하고 `_variation_ratio`를 적용합니다.
    - 스케일별 TVR을 기하평균으로 합성해 `tvr`를 계산합니다.
  - `_persistence_components`  
    - `_time_under_water`로 `tuw`를 구하고, 이를 기반으로 `nh_frac(=1 - tuw)`를 계산합니다.
  - `_normalized_drawdown`  
    - `_max_drawdown`과 `net_gain`을 이용해 드로다운을 정규화(`mdd_norm`)합니다.

- 스코어 집계 전략
  - `_LinearityComponents` dataclass  
    - `r2_up`, `spearman_rho`, `tvr`, `tuw`, `nh_frac`, `mdd_norm`, `net_gain` 등을 한 구조체로 모읍니다.
  - `_HarmonicMeanLinearityStrategy`  
    - 방향 일관성(원시 `raw_gain`이 `orientation`과 부합하는지)을 먼저 검사합니다.
    - trend(√(r2_up × ρ⁺)), smooth(TVR), persistence(nh_frac), DD penalty(1/(1 + mdd_norm)) 네 컴포넌트를 모두 `(0, 1]`로 클램프한 뒤 조화평균으로 합성합니다.
  - `equity_linearity_metrics_v2`  
    - 위 템플릿과 전략을 조합하는 얇은 함수로 단순화되어, CC가 A 등급으로 개선되었습니다.

## compute_alpha_performance_summary 리팩터링

### 기존 문제

- 하나의 함수 안에서:
  - NaN 필터링
  - 현실적 비용/고정 transaction_cost 분기
  - 초과수익 계산과 샤프/드로다운/비율 계산
  - alpha_performance prefix 부여 및 execution_* 메트릭 머지가 모두 수행되었습니다.
- 로직 이해와 테스트, 재사용이 어려운 구조로 CC가 C(13)이었습니다.

### 개선된 구조

- 입력 정제/비용 반영
  - `_clean_returns`  
    - NaN을 제거하고 `float`로 캐스팅된 수익률 시퀀스를 반환합니다.
  - `_net_returns_and_execution_metrics`  
    - `use_realistic_costs`와 `execution_fills` 유무에 따라:
      - 현실적 비용 모드: `adjust_returns_for_costs` + `calculate_execution_metrics`
      - 단순 비용 모드: `transaction_cost`를 매 기간 차감
    - 순수익률(`net_returns`)과 실행 메트릭(`execution_metrics`)을 한 번에 결정합니다.

- 핵심 알파 메트릭 계산
  - `_excess_returns` / `_sharpe_ratio`
  - `_alpha_core_metrics`  
    - `sharpe`, `max_drawdown`, `win_ratio`, `profit_factor`, `car_mdd`, `rar_mdd`를 계산합니다.

- 상위 템플릿 함수
  - `compute_alpha_performance_summary`는 이제 다음 역할에 집중합니다.
    - 입력 클린업 → 비용 반영 → 핵심 메트릭 계산 → prefix/실행 메트릭 merge
  - 결과는 기존과 동일한 스키마(`alpha_performance.<metric>`, `execution_<metric>`)를 유지하며, CC는 A 등급으로 개선되었습니다.

## WorldService: augment_metrics_with_linearity 리팩터링

### 기존 문제

- 서비스 계층 함수 `augment_metrics_with_linearity`가 다음을 모두 수행하고 있었습니다.
  - per-strategy equity 시계열 materialize
  - v1/v2 선형성 메트릭 계산 및 주입
  - per-strategy alpha 메트릭 계산 및 주입
  - 포트폴리오 equity 구성 및 선형성/알파 메트릭 주입
- 로직이 길어지고 역할이 섞여 있어, 다른 선형성/알파 변형을 추가하기 어려운 구조였습니다.

### 개선된 구조

- 전략형 보조 객체 도입
  - `_LinearityMetricsAugmentor` 클래스
    - `augment(metrics, series)`  
      - 기존 `augment_metrics_with_linearity`의 템플릿 역할 담당.
      - 입력 메트릭 맵을 복사하고, per-strategy 및 포트폴리오 메트릭을 순서대로 추가합니다.
    - `_extract_equity_series`  
      - `_materialize_equity_curve`를 사용해 strategy별 equity를 만들고, v1/v2 선형성 + alpha 메트릭을 슬롯에 주입합니다.
    - `_augment_with_portfolio_metrics`  
      - 공통 포트폴리오 equity를 생성하고, 선형성/알파 메트릭을 per-strategy 슬롯에 주입합니다.
  - 전역 함수 `augment_metrics_with_linearity`는 `_LinearityMetricsAugmentor().augment(...)`를 호출하는 얇은 래퍼로 축소되어, 서비스 API 계약은 그대로 유지됩니다.

## radon 및 검증 전략

- radon CC 목표
  - `equity_linearity_metrics_v2`: C → A
  - `compute_alpha_performance_summary`: C → A
  - `augment_metrics_with_linearity`: A를 유지하되, 관련 로직을 `_LinearityMetricsAugmentor`로 분리해 향후 확장을 용이하게 함.
- 테스트 전략
  - 선형성 메트릭:
    - `tests/qmtl/runtime/transforms/test_equity_linearity.py`
    - `tests/qmtl/runtime/transforms/test_equity_linearity_v2.py`
  - 알파 메트릭:
    - `tests/qmtl/runtime/test_alpha_metrics.py`
  - WorldService wiring:
    - `tests/qmtl/services/worldservice/test_linearity_wiring.py`
- 성능/숫자 정확도
  - 기존 테스트 스위트를 재사용해 숫자적 동작을 회귀 검증합니다.
  - OLS/통계 계산은 기존 구현을 헬퍼/템플릿으로 분리한 형태이기 때문에, 알고리즘 복잡도는 유지되면서 가독성과 재사용성이 향상됩니다.

## 향후 확장 포인트

- 새로운 선형성/알파 지표 추가 시:
  - transforms/helpers 계층에서는 헬퍼/전략 객체를 확장합니다.
  - WorldService 계층에서는 `_LinearityMetricsAugmentor` 또는 유사한 전략형 보조 객체만 수정해 서비스 계약을 유지합니다.
- radon 관점에서:
  - 새 메트릭 도입 시에도 템플릿/전략 구조를 재사용해 C급 함수가 다시 늘어나지 않도록 합니다.
  - 정기적인 radon 스냅샷 문서(예: 2025-11-14 스냅샷)와 연동해, 복잡도가 상승하는 지점을 조기에 탐지합니다.

