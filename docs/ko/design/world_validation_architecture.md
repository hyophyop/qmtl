---
title: "World 검증 계층 확장 설계 스케치"
tags: [design, world, validation, core-loop]
author: "QMTL Team"
last_modified: 2025-12-13
status: draft
---

# World 검증 계층 확장 설계 스케치

!!! abstract "목표"
    이 문서는 QMTL WorldService의 **검증(Validation) 계층**을 고도화하기 위한 확장 설계 초안이다.  
    목표는 **소규모 조직도 “기술로 리스크를 제어할 수 있을 만큼 신뢰도 높은 검증 단계를 갖추는 것**이며,  
    Core Loop × World 로드맵의 Phase 4–5를 뒷받침하는 세부 설계를 제공한다.

관련 문서:

- 아키텍처 개요 및 Core Loop: [architecture/architecture.md](../architecture/architecture.md)
- World 사양: [world/world.md](../world/world.md)
- WorldService 평가 런 & 메트릭 API: [design/worldservice_evaluation_runs_and_metrics_api.md](worldservice_evaluation_runs_and_metrics_api.md)
- Core Loop × WorldService 자동화 아키텍처: [architecture/core_loop_world_automation.md](../architecture/core_loop_world_automation.md)
- 모델 리스크 관리 프레임워크: [design/model_risk_management_framework.md](model_risk_management_framework.md)
- 과거 SDK auto_returns 설계(보관용): [archive/auto_returns_unified_design.md](../archive/auto_returns_unified_design.md)

> 최근 변경 요약 (risk_signal_hub 연계)
> - Hub 최소 구현: WS에 `risk_hub` 라우터를 추가하고 dev(in-memory/SQLite+fakeredis 캐시, offload 비활성)·prod(Postgres+Redis+S3/redis)에서 스냅샷 메타를 영속화하도록 바인딩.
> - 소비자 전환: `ExtendedValidationWorker`가 hub 스냅샷(가중치/공분산) 기반으로 Var/ES 베이스라인을 계산하도록 수정하여 gateway 직접 의존을 제거.
> - 생산자/이벤트 경로 정착: gateway가 리밸런스·체결 이후 스냅샷을 push하고(`qmtl/services/gateway/risk_hub_client.py`), ControlBus(CloudEvents)로 `risk_snapshot_updated`/activation/evaluation run 업데이트 이벤트를 발행·소비하도록 표준 템플릿을 적용함.
> - 환경 설정 일원화: `qmtl.yml` `risk_hub` 블록(dev=inline+fakeredis 캐시만, prod=Postgres+Redis+S3/redis)으로 WS 라우터 토큰/inline offload/blob 스토어와 gateway push 클라이언트를 동시에 구성하도록 연결.

---

## 구현 트래킹 (post v1.5)

- v1.5 구현/closeout 상태: `docs/ko/design/world_validation_v1.5_implementation.md`
- Epic: #1941 (본 문서 설계의 v1.5 이후 잔여 구현 트래킹)

- [x] #1942 Advanced metrics pack 구현 (tail/regime/CV/complexity)
- [x] #1943 Paper/ShadowConsistencyRule 구현 + DSL 지원
- [x] #1944 Benchmark/Challenger 메트릭 저장 + 상대평가 룰
- [x] #1945 Cohort/Campaign 평가 모델 도입 + CohortRule 고도화
- [x] #1946 Active portfolio snapshot 기반 incremental VaR/ES 산출
- [x] #1947 Stress scenario contract/메트릭/룰 고도화 (stress_ref)
- [x] #1948 Independent Validation 운영 모델 정착 (권한/CI 강제)
- [x] #1949 EvaluationRun 이벤트 기반 비동기 검증 파이프라인 구축
- [x] #1950 Validation SLO/시나리오/부하 테스트 + CI 게이트

## 0. 배경 & 문제 정의

현재 v2 아키텍처에서 WorldService는 다음 역할을 갖는다.

- 월드 정책(WorldPolicy)에 따라 전략을 평가·선정하고 실행 모드를 관리한다.
- Evaluation Run 모델을 통해 전략 제출/검증/활성화 단계를 추적한다.
- `/evaluate`·`/activation`·`/allocations`를 통해 Core Loop 상의 “승격/강등/배분” 결정을 노출한다.

그러나 **검증 단계 자체의 구조와 확장성**은 아직 다음과 같은 과제를 갖는다.

- 검증 규칙(데이터 통화성, 샘플 충분성, 성과/리스크 컷, 과적합/취약성 신호 등)이
  - 코드에 흩어져 있거나,
  - DSL 상에서 충분히 구조화되어 있지 않아,
  - 실제 실패를 관찰한 뒤 검증을 강화하는 루프가 어렵다.
- Evaluation Run의 메트릭 스키마가 **어떻게 확장될지**(새 지표를 어떻게 추가·소비할지)가 명확하지 않다.
- 소규모 조직에서 사람이 일일이 검토하기엔
  - 후보 전략 수가 많고,
  - 시장/전략 종류가 달라서
  - “검증을 코드로 강화할 수 있는 여지”가 중요하지만, 이를 전제로 한 설계가 충분히 정리되어 있지 않다.

이 문서는 위 문제를 해결하기 위해,

1. **지표 스키마(Evaluation Metrics)의 확장 가능 구조**,  
2. **룰 기반 검증 파이프라인(Validation Rules)의 모듈 구조**,  
3. **World 정책 DSL과의 연결 방식**,  
4. **실패 → 검증 강화 피드백 루프**

를 하나의 설계로 정리하는 것을 목표로 한다.

### 0.1 범위와 비범위

본 문서는 **WorldService 검증 계층**에 초점을 둔다. 따라서 다음 항목은 의도적으로 스코프 밖에 둔다.

- 전략 아이디어/팩터의 이론적 타당성 검토, 학술적 배경 정리
- 전략 코드 품질, 유닛/통합 테스트, 배포 파이프라인 설계
- PM·운용 위원회 의사결정 프로세스, 인센티브/보상 구조

이 영역들은 “모델 개발/사용”과 조직·거버넌스 설계 문서에서 다루며, 본 문서는 **“이미 제출된 전략이 World 안에서 어느 단계까지 올라갈 수 있는지”를 결정하는 검증·모니터링 계층**만을 다룬다.

### 0.2 Runner/SDK/WorldService 역할 (returns/지표)

본 설계는 returns/지표/검증을 **항상 World/WorldService 평가 파이프라인에서 계산**한다는 전제를 둔다.

- SDK/Runner는 전략 제출과 EvaluationRun/지표 조회에만 집중한다.
  - `Runner.submit(..., world="...")`는 dev/prod 모두 World/WS 경로를 통해 EvaluationRun과 메트릭을 생성한다.
  - SDK는 `SubmitResult.evaluation_run_id` 또는 WS 링크만 받고,  
    필요 시 별도 헬퍼(예: `Runner.poll_evaluation(world, run_id, ...)`)로 지표가 준비되었는지 확인한 뒤 EvaluationRun/EvaluationMetrics를 조회한다.
- returns/metrics의 **검증 SSOT는 WorldService** 이다.
  - SDK는 로컬 편의를 위해 `auto_returns` 등으로 returns를 만들 수 있지만, 이는 **precheck 입력/참고 정보**이며 정책 평가/게이팅의 최종 결정은 WS 평가 결과를 따른다.
  - World 평가에서 사용하는 returns/메트릭은 최종적으로 WS가 저장한 EvaluationRun/metrics를 기준으로 운영·감사 가능해야 한다.
- dev/prod 두 스택:
  - dev 스택에서는 로컬/테스트용 WorldService/Gateway/Seamless 구성을 사용하지만,  
    prod와 동일한 “제출 → EvaluationRun → 지표 조회” 플로우를 그대로 사용한다.
  - 로컬 DX는 (선택적 편의 기능 포함) dev World에서 prod와 동일한 경로/결과 구조를 실행할 수 있게 하는 것을 목표로 한다.

과거 SDK auto_returns 설계는 [`archive/auto_returns_unified_design.md`](../archive/auto_returns_unified_design.md)에 아카이브되어 있으며,  
이 문서는 World/WS 기반 평가 모델을 기준으로 검증 계층을 정의한다.

### 0.3 Runner.wait_for_evaluation 헬퍼 (dev/prod 공통)

- Runner는 WS EvaluationRun 상태/지표를 조회하는 폴링 헬퍼를 제공한다.
  - `Runner.wait_for_evaluation(..., timeout=300, interval=runtime.POLL_INTERVAL_SECONDS)` 또는 async 버전을 사용한다.
  - `run_id`(또는 `evaluation_run_url`)와 `strategy_id`/`world`는 `SubmitResult`로부터 그대로 전달한다.
  - 반환값은 `summary.status`·`summary.recommended_stage`·metrics dict 등을 담은 `EvaluationRunStatus` 이다.
- dev/prod 모두 `Runner.submit` 이후 동일하게 사용 가능하다.

```python
from qmtl.runtime.sdk import Runner
from scripts.generate_validation_report import generate_markdown_report

submit_result = Runner.submit(MyStrategy, world="dev-world")
eval_status = Runner.wait_for_evaluation(
    world=submit_result.world,
    run_id=submit_result.evaluation_run_url or submit_result.evaluation_run_id,
    strategy_id=submit_result.strategy_id,
    timeout=180,
    interval=5,
)

report_markdown = generate_markdown_report(
    eval_status.to_dict(),
    model_card={"strategy_id": submit_result.strategy_id},
)
```

---

## 1. 설계 원칙

World 검증 계층은 다음 설계 원칙을 따른다.

1. **WS SSOT & 모드 분리**
   - 실행 모드/단계의 단일 진실 소스는 WorldService `effective_mode`/정책 결과다.
   - 검증 계층은 “이 전략이 어떤 단계까지 올라갈 수 있는지”를 판정할 뿐,
     Runner/SDK가 모드를 직접 승격하지 않는다.

2. **레이어드 방어(Defense in Depth)**
   - 검증은 하나의 거대한 조건문이 아니라, 여러 레이어의 룰로 나뉜다.
     - 데이터/샘플 레이어
     - 성과/리스크 컷 레이어
     - 구조적 제약(상관/익스포저 등) 레이어
     - 로버스트니스/과적합 신호 레이어
     - paper/shadow 리허설 레이어
   - 각 레이어는 독립적으로 pass/fail/warn를 낼 수 있어야 하고,  
     World 정책은 어떤 레이어 위반으로 후보에서 탈락했는지 표시할 수 있어야 한다.

3. **지표 스키마 확장성**
   - Evaluation Run 메트릭 스키마는 **“핵심 필드 + 확장 슬롯”** 구조로 설계한다.
   - 새로운 실패 패턴을 발견했을 때,
     - Runner/ValidationPipeline에서 새 지표를 계산해 WS로 보내고,
     - World 정책 DSL에서 이를 곧바로 소비할 수 있어야 한다.

4. **검증 룰의 모듈성**
   - 검증 로직은 C++식 거대한 if-else가 아니라,
     - 작은 Rule 객체(또는 함수)들의 집합으로 표현한다.
   - World 정책 DSL은 “어떤 룰을 어떤 파라미터로 활성화할지”만 선언한다.
   - 실패가 발견되면 새 Rule을 추가하거나 기존 Rule의 파라미터만 조정해도 대응이 가능해야 한다.

5. **운영자/리스크 관점에서 “이해 가능한 복잡도” 유지**
   - DSL과 Rule 세트는 “한 페이지 설명”이 가능한 수준을 유지해야 한다.
   - 검증이 너무 복잡해져서 아무도 무슨 일이 일어나는지 이해하지 못하면,
     시스템 신뢰도는 오히려 떨어진다.

### 1.1 모델 리스크 관점과 Risk Tiering

전통적인 모델 리스크 관리(MRM, 예: SR 11‑7) 관점에서는 “모델 개발/사용 – 모델 검증 – 거버넌스/통제”의 세 축을 요구한다. World 검증 계층은 이 중 **“검증” 축**을 강화하는 설계이지만, **World/전략별 리스크 티어링**과 **모델 정의/문서화(Model Card)**를 도입하면 전체 Core Loop의 신뢰도를 한 단계 끌어올릴 수 있다.

- `risk_profile` 필드(예시)는 world 또는 WorldPolicy에 추가한다.

  ```yaml
  risk_profile:
    tier: high | medium | low          # 자본 영향도/복잡도 기반 티어
    max_capital_at_risk_pct: 2.0       # 전체 운용 자본 대비 허용 손실 비중
    client_critical: true | false      # 대외/수탁 자금 포함 여부
  ```

- Tier에 따라:
  - 필수 레이어 세트가 달라질 수 있다. 예: `tier=high`는 Data/Sample/Performance/Risk/Robustness/Paper 레이어를 모두 blocking 으로 요구하고, `tier=low`는 일부를 warn 모드로만 운용.
  - 동일 Rule이라도 티어에 따라 Sharpe/MDD/ES 등 컷을 다르게 가져간다.

또한 각 전략에 대해 간단한 **Model Card**(model/spec 문서)를 정의하고, Evaluation Run에는 `model_card_version`을 연결한다.

- Model Card에는 목적, 사용 데이터/피처, 타임프레임, 핵심 가정, 한계 등을 기록한다.
- 나중에 문제가 난 전략에 대해 “어떤 가정과 validation 정책 아래 승인되었는지”를 Evaluation Run 수준에서 추적할 수 있다.

---

## 2. Evaluation Run 메트릭 스키마 확장

### 2.1 코어 메트릭 블록 구조

WorldService 평가 런 문서에서 제안한 모델을 확장해, Evaluation Run 메트릭을 다음 블록으로 나눈다.

- `returns`: 순수 전략 수익률 시계열 요약 (샘플 수, 윈도우, Sharpe, MDD, 변동성 등)
- `pnl`: 계좌/통화 단위 PnL 요약 (총 PnL, PnL max drawdown 등) — 필요 시
- `sample`: 샘플 충분성과 관련된 지표 (거래일 수, 거래 횟수, notional turnover 등)
- `risk`: 익스포저, 레버리지, 섹터 concentration 등 구조적 리스크
- `robustness`: 롤링 Sharpe, 앞/뒤 구간 성과 차이, 파라미터 민감도 프록시 등
- `diagnostics`: 기타 디버깅용/실험적 지표

스키마 초안(개념적):

```json
{
  "world_id": "crypto_mom_1h",
  "strategy_id": "beta_mkt_simple",
  "run_id": "2025-12-02T10:00:00Z-uuid",
  "returns": { "...": "..." },
  "pnl": { "...": "..." },
  "sample": { "...": "..." },
  "risk": { "...": "..." },
  "robustness": { "...": "..." },
  "diagnostics": {
    "extra_metrics": {
      "my_custom_metric": 0.123,
      "another_metric": -0.5
    }
  }
}
```

핵심 아이디어:

- 각 블록은 **내부적으로 Pydantic 모델 또는 유사 구조**로 관리하고,
- `diagnostics.extra_metrics`는 “실험적 지표/추후 승격 후보”를 넣는 확장 슬롯이다.
- World 정책 DSL은 코어 블록만을 대상으로 사용해도 되고,
  필요 시 `diagnostics.extra_metrics["foo"]` 같은 키를 직접 참조하는 규칙도 허용할 수 있다.

### 2.2 지표 추가 플로우

새로운 실패 패턴을 관찰했을 때:

1. Runner/ValidationPipeline에 해당 패턴을 측정하는 지표를 추가한다.
2. WS Evaluation Run 메트릭 모델에 필드를 추가하거나, `diagnostics.extra_metrics`에 값을 넣는다.
3. World 정책 DSL에 해당 지표를 사용하는 룰을 추가한다.

이때 기존 정책/코드는 **새 필드를 모르면 무시**하는 방향으로 설계해,  
점진적인 롤아웃이 가능하도록 한다.

### 2.3 업계 수준 지표 확장 (과적합/다중 테스트 통제)

“소규모 조직에서 쓸 수 있는 검증”을 넘어 **업계에서 통용되는 MRM/과적합 통제 관행**을 반영하려면, 다음 축의 지표를 1급 개념으로 추가하는 것이 유효하다.

- **Sample/Data 축**
  - `effective_history_years`: 실제 거래일·유효 데이터 기준 연수.
  - `n_trades_total`, `n_trades_per_year`: 총/연평균 트레이드 수.
  - `regime_coverage`: 고/중/저 변동성 구간별 거래일/트레이드 비중.
  - 이 값들을 이용해 “최소 X년 + 최소 Y 트레이드 + 적어도 하락장 레짐 1회 이상 포함” 같은 형태의 SampleRule을 정의할 수 있다.

- **Performance/Risk 축 (Tail/Shape/Path)**
  - Tail 지표: `var_p01`, `es_p01`(1% VaR/ES), `pnl_tail_index`(파레토 꼬리 지수 프록시 등).
  - Shape 지표: `skew`, `kurtosis`.
  - Path 지표: `avg_dd_recovery_time`(평균 DD 회복 기간), `max_consecutive_losses_trades/days`.
  - PerformanceRule/RiskConstraintRule이 단순 Sharpe/MDD 컷을 넘어 tail/경로 특성을 활용할 수 있다.

- **Robustness 축 (과적합/다중 테스트)**
  - `probabilistic_sharpe_ratio`(PSR), `deflated_sharpe_ratio`(DSR), `min_track_record_length`.
  - time‑series cross‑validation 결과:
    - `cv_folds`(purged & embargoed CV fold 수),
    - `cv_sharpe_mean`, `cv_sharpe_std`,
    - `cv_dd_p95`(각 fold DD 95% 분위수) 등.
  - RobustnessRule은 “out‑of‑sample 일관성”과 “과도하게 좋은 Sharpe의 통계적 신뢰도”를 함께 검증할 수 있다.

- **Diagnostics 축 (복잡도/탐색 강도)**
  - `strategy_complexity`: 파라미터 수, 코드 cyclomatic complexity, 피처 차원 등으로부터 유도한 복합 지표.
  - `search_intensity`: 캠페인 내 실험한 변형 개수, 총 백테스트 횟수, 하이퍼파라미터 탐색 예산 등.
  - 이 값들은 “복잡도·탐색 강도가 높을수록 Sharpe 신뢰도를 더 깎는다”는 형태의 규칙에 활용할 수 있다.

---

## 3. 검증 파이프라인 구조 (Validation Rules)

### 3.1 룰 타입 분류

검증 룰은 크게 다음 카테고리로 나눈다.

1. **DataCurrencyRule**  
   - 데이터 통화성, 커버리지, missing ratio 등.
   - 필요 시 입력 데이터 품질(결측/이상치 비율, 베이스라인 벤더/스키마 변경 이벤트) 점검을 포함할 수 있다. 데이터 라인리지·품질 자체의 상세 설계는 별도의 데이터 인프라 문서에서 다루되, DataCurrencyRule은 해당 신호를 소비하는 진입점 역할을 한다.
2. **SampleRule**  
   - `sample_days`, `trades_60d`, `notional_turnover` 등 샘플 충분성.
3. **PerformanceRule**  
   - Sharpe, MDD, volatility, profit_factor 등 성과/리스크 컷.
4. **RobustnessRule**  
   - 롤링 윈도우 성과, 앞/뒤 반기 Sharpe 차이, drawdown episode 분포 등.
5. **RiskConstraintRule**  
   - 익스포저/레버리지/섹터 및 상관 제약.
6. **Paper/ShadowConsistencyRule** (선택)  
   - paper/shadow 결과가 backtest 특성과 크게 어긋나지 않는지 확인.

각 Rule은 다음 인터페이스를 따른다(의사 코드):

```python
class ValidationRule(Protocol):
    name: str

    def evaluate(self, metrics: EvaluationMetrics, context: RuleContext) -> RuleResult:
        ...
```

`RuleResult`는 최소한 다음 정보를 포함한다.

- `status`: "pass" | "fail" | "warn"
- `reason`: string (사람이 읽을 수 있는 사유)
- `details`: dict (추가 디버깅 정보)

### 3.3 Rule 심각도·소유자 메타데이터

운영/리스크/퀀트 팀 간에 “어떤 룰이 진짜 gate인지”를 명확히 하기 위해, 각 RuleResult에 다음 메타데이터를 추가한다.

- `severity`: `"blocking" | "soft" | "info"`
  - `blocking`: fail 시 해당 단계 진입 불가.
  - `soft`: fail 시 가중치/점수에서 페널티만 부여.
  - `info`: 참고 정보만 제공, 승격/강등에는 직접 사용하지 않음.
- `owner`: `"quant" | "risk" | "ops"`
  - 관리 주체(퀀트/리스크/운영)를 명시해 변경 책임을 분리한다.

의사 코드:

```python
class RuleResult(BaseModel):
    status: Literal["pass", "fail", "warn"]
    severity: Literal["blocking", "soft", "info"] = "blocking"
    owner: Literal["quant", "risk", "ops"] = "quant"
    reason: str
    details: dict[str, Any] = {}
```

World 정책 DSL에서는 다음과 같이 사용한다.

```yaml
validation:
  performance:
    sharpe_mid:
      min: 0.8
      severity: blocking
      owner: risk
  robustness:
    dsr_min:
      min: 0.4
      severity: soft
      owner: quant
```

### 3.4 Cohort/Portfolio/Stress Rule 유형

단일 Evaluation Run(단일 전략)만 보는 Rule 외에, **캠페인/포트폴리오/스트레스 시나리오** 단위의 Rule을 도입하면 업계 수준의 검증에 더 가깝게 다가갈 수 있다.

- **CohortRule (캠페인 단위 룰)**  
  - 여러 전략 후보를 한 번에 평가해 다중 테스트/랭킹 기반 규칙을 적용한다.
  - 예: “이번 캠페인에서 DSR 상위 k개만 live 후보로 남기기”, “Sharpe>4 전략이 나오면 캠페인 전체 warn 처리”.

  ```python
  class CohortRule(Protocol):
      name: str
      def evaluate(
          self,
          metrics_list: list[EvaluationMetrics],
          context: RuleContext,
      ) -> dict[str, RuleResult]:  # run_id -> RuleResult
          ...
  ```
  - 가능하다면 단순 Buy&Hold, cap‑weighted index, naive factor(예: 단순 모멘텀/밸류)와 같은 **벤치마크/챌린저 모델 메트릭**을 함께 받아, 후보 전략의 성과·리스크를 벤치마크 대비 상대적으로 평가하는 확장 포인트를 열어 둔다.

- **PortfolioRule (기존 포트폴리오 대비 인크리멘탈 룰)**  
  - 새 전략과 기존 live 전략 집합의 조합을 보고 Incremental VaR/ES, 포트폴리오 Sharpe 개선 여부 등을 평가한다.
  - DSL 예:

    ```yaml
    validation:
      portfolio:
        max_incremental_var_99: 0.5
        min_portfolio_sharpe_uplift: 0.1
    ```

- **StressRule (스트레스 시나리오 룰)**  
  - 미리 정의된 시장 시나리오(“2008 금융위기”, “2020 코로나 쇼크” 등)에 대해
    재시뮬레이션한 PnL/DD를 입력으로 사용한다.
  - Evaluation Metrics에 `"stress"` 블록을 두고, 각 시나리오별 DD/ES 컷을 검증한다.

### 3.2 룰 구성 및 실행 전략

- World 정책 DSL은 “활성화할 룰과 파라미터”만 정의한다.
- WorldService는 DSL을 파싱하여 룰 인스턴스를 구성하고, Evaluation Run 메트릭에 대해 순차/병렬 평가를 수행한다.
- 룰 실행 결과는 Evaluation Run의 `validation` 섹션에 기록한다.

예시(개념적):

```yaml
validation:
  data_currency:
    max_lag: 5m
    min_history: 180d
  sample:
    min_sample_days: 90
    min_trades_180d: 60
  performance:
    sharpe_mid:
      min: 0.8
    max_dd_180d:
      max: 0.25
  robustness:
    rolling_sharpe_min: 0.5
    max_regime_gap: 0.4
  risk:
    exposure:
      max_leverage: 3.0
      sector_cap: 0.3
    tail:
      p01_daily_return_min: -0.08
```

이 DSL은 내부적으로 다음 Rule 인스턴스 집합으로 변환된다.

- `DataCurrencyRule(max_lag=5m, min_history=180d)`
- `SampleRule(min_sample_days=90, min_trades_180d=60)`
- `PerformanceRule(sharpe_mid_min=0.8, max_dd_180d_max=0.25)`
- `RobustnessRule(rolling_sharpe_min=0.5, max_regime_gap=0.4)`
- `RiskConstraintRule(max_leverage=3.0, sector_cap=0.3, p01_min=-0.08)`

---

## 4. World 정책 DSL과의 통합

### 4.1 `validation` 블록 역할 재정의

`world/world.md`의 정책 DSL을 다음과 같이 역할 분리한다.

- `validation:`  
  - **live/paper 후보군에 오르기 위한 최소 조건**을 정의한다.
  - validation을 통과하지 못한 전략은 selection/top‑k/hysteresis 단계에 진입하지 못한다.
- `selection:`  
  - `gates/score/topk/constraints/hysteresis`는 validation을 통과한 후보들 중에서  
    “어떤 전략을 어느 비중으로 쓸지”를 결정한다.

이렇게 하면 검증 계층이 **“후보군 필터”** 역할을 맡고,  
selection 계층은 **“후보군 안에서의 상대적 선택/유지”**를 담당하게 된다.

### 4.2 실행 단계 추천값

검증 결과는 “통과/실패”에 더해 **추천 실행 단계**를 반환할 수 있다.

- `recommended_stage`: `backtest_only | paper_only | paper_ok_live_candidate`

World 정책은 이 값을 사용해:

- 특정 전략은 “백테스트만 반복”하거나,
- 일정 조건을 만족하면 “paper까지 허용”하고,
- 충분한 검증을 통과한 전략만 “live 후보 리스트”에 올릴 수 있다.

live로의 실제 전환은 기본적으로 `/apply` 또는 별도 운영 승인 플로우에 남겨두되,  
검증 계층은 “live 후보가 될 자격이 있는지”를 엄격히 필터링하는 역할을 한다.

### 4.3 Validation Profile & Policy Versioning

World 정책 DSL은 단일 `validation` 블록만 갖는 대신, **단계별 Validation Profile**과 **정책 버전** 개념을 도입할 수 있다.

- 예시:

  ```yaml
  validation_profiles:
    backtest:
      # 매우 느슨한 컷 + 과적합 경고 위주
    paper:
      # data/sample/performance 강하게 + robustness는 warn
    live:
      # robustness/risk까지 blocking

  default_profile_by_stage:
    backtest_only: backtest
    paper_only: paper
    paper_ok_live_candidate: live
  ```

- WorldService는 `recommended_stage`와 `default_profile_by_stage` 매핑을 이용해  
  어떤 프로파일을 적용할지 결정한다.
- 각 Evaluation Run에는 `validation_policy_version` 및 `ruleset_hash`를 기록해,
  정책 변경 전후 diff를 오프라인에서 시뮬레이션하고, 경고 모드 → fail 승격 과정을 안전하게 진행할 수 있다.

---

## 5. 실패 → 검증 강화 피드백 루프

### 5.1 실패 케이스 수집

운영상에서 다음과 같은 이벤트가 발생했을 때:

- paper/live 전략이 예상보다 큰 손실을 내거나,
- 검증 단계에서 통과시켰으나 “명백한 취약성”이 드러났을 때,

WorldService는 해당 전략/월드/Run에 대한 다음 정보를 함께 기록·조회할 수 있어야 한다.

- Evaluation Run 메트릭 스냅샷
- 적용되었던 world policy 버전 및 validation 파라미터
- Rule별 평가 결과(`RuleResult`)와 status/reason

### 5.2 검증 강화 절차

실패가 관찰되면:

1. 어떤 Rule이 해당 실패를 잡을 수 있었는지, 또는 새 Rule이 필요한지를 분석한다.
2. Runner/ValidationPipeline/WS에 새 지표 또는 Rule을 추가한다.
3. 기존 Evaluation Run 히스토리에 대해 “새 Rule을 적용했을 때 어떻게 달라졌을지”를 오프라인으로 시뮬레이션한다.
4. 일정 기간 경고 모드(`status=warn`)로만 운영해 보며 영향 범위를 관찰한 뒤,
5. 최종적으로 해당 Rule을 `fail` 모드로 승격한다.

이 절차를 지원하기 위해:

- Evaluation Run 지표·Rule 결과는 **append-only 히스토리**로 보존하고,
- policy 변경 전후의 diff를 비교하는 도구(스크립트/리포트)를 제공하는 것이 바람직하다.

### 5.3 운영·거버넌스·Live 모니터링

기술적 검증 설계 외에도, 업계 수준 신뢰도를 위해서는 운영·거버넌스·툴링이 함께 설계되어야 한다.

- **독립 검증(Independent Validation)**
  - validation 룰 구현과 World 정책 DSL 저장소를 전략 코드 저장소와 분리한다.
  - 변경 워크플로:
    - 전략 코드: 퀀트 팀 주도.
    - validation 룰/정책: 리스크/검증 담당자만 merge 권한.
  - 모든 룰/정책 변경 시, 영향 받는 World/전략 수와 대표 “나쁜 전략” 세트에 대한 regression test 결과를 CI에서 강제한다.

- **Live 전략 상시 재검증(Live Monitoring)**
  - 매일/매주 자동 “Live Evaluation Run”을 생성하고, 최근 30/60/90일 실현 PnL/Sharpe/DD/ES 및 backtest 대비 성과 드리프트를 측정한다.
  - DSL에 `live_monitoring` 블록을 추가해, 일정 기간 동안의 실현 지표가 기준을 벗어나면 자동 demotion 후보로 태깅하거나 수동 검토 대상으로 올린다.

- **Evaluation Store & 테스트 세트**
  - Evaluation Run 전체를 하나의 불변 아티팩트(메트릭·Rule 결과·코드 hash·데이터 snapshot·policy 버전)를 담는 “Evaluation Store”로 관리한다.
  - 대표적인 실패 모드별 “나쁜 전략” 세트를 만들어, validation 변경 시마다 이 세트에 대해 어떤 룰이 어떤 이유로 fail을 내는지 regression test를 수행한다.

- **Fail‑closed 기본값**
  - Validation 파이프라인에서 예외/에러 발생 시 기본값은 pass가 아니라 fail(또는 “검증 실패 – 재시도 필요”)로 처리한다.
  - DSL에 다음과 같은 옵션을 두어 World별 보수성을 조정할 수 있다.

    ```yaml
    validation:
      on_error: fail | warn
      on_missing_metric: fail | warn | ignore
    ```

  - 특히 high‑tier world에서는 오류/누락 시 항상 fail‑closed 경로를 타도록 권장한다.

- **Validation Report/Artefact**
  - 각 World/전략에 대해 Evaluation Run·Rule 결과를 요약한 **Validation Report**를 표준 포맷(요약, 스코프, 사용 지표·룰, 결과, 한계, 권고사항 등)으로 생성·보관한다.
  - 보고서 템플릿·배포 경로는 운영 문서(예: `operations/activation.md` 또는 별도 MRM 문서)에서 정의하되, 이 설계는 Validation Report가 Evaluation Store의 스냅샷을 사람이 읽을 수 있는 형태로 투영한 산출물임을 전제로 한다.

---

## 6. 로드맵 연계 및 다음 단계

이 문서의 설계는 “Core Loop × WorldService 자동화 아키텍처”의 캠페인/거버넌스(Phase 4–5)와 직접 연결된다.

- Core Loop 자동화(정리본): [architecture/core_loop_world_automation.md](../architecture/core_loop_world_automation.md)
- (아카이브) 단계별 작업 로드맵: [archive/core_loop_world_roadmap.md](../archive/core_loop_world_roadmap.md)

- **Phase 4**:  
  - 여기서 정의한 Evaluation Run 메트릭 블록 구조 및 캠페인 상태 모델을 사용해  
    backtest/paper/live 캠페인 윈도우를 관리한다.
- **Phase 5**:  
  - `validation` 블록과 Rule 세트가 “충분히 신뢰할 수 있는 검증 단계”를 제공하도록 확장/튜닝한다.

### 작업자용 다음 스텝 제안

1. **코어 지표 세트 확정**  
   - returns/sample/performance/risk/robustness 블록에 들어갈 “최소 필수 필드”를 일단 고정한다.
2. **첫 번째 Rule 세트 구현**  
   - DataCurrency/Sample/Performance/RiskConstraint 중심의 작은 Rule 세트를 구현하고,  
     world policy 예제에 `validation` 블록을 추가한다.
3. **Rule 결과/지표 리포트 형식 정의**  
   - Evaluation Run API 혹은 별도 리포트에서 Rule별 결과와 사유를 어떻게 보여줄지 스케치한다.
4. **실패 케이스를 반영한 반복 프로세스 설계**  
   - 실패 → 새 지표/Rule 추가 → 경고 모드 → fail 승격까지의 워크플로를  
     운영 문서(operations/activation.md 또는 신규 문서)에 요약해 둔다.

이 문서는 의도적으로 “스케치 수준”으로 남겨 두고, 실제 구현이 진행되면서  
구체적인 지표 목록, Rule 타입, DSL 스키마를 채워가는 것을 전제로 한다.

---

## 7. 참조 스키마 & DSL 예제 (v1 제안)

이 섹션은 실제 구현·정책 작업자가 바로 참조할 수 있도록, 위에서 논의된 개념들을 **v1 기준으로 정리한 스케치 스키마**를 제공한다. 필드/타입은 초안이며, 구현 단계에서 세부 이름과 구조는 조정될 수 있다.

### 7.1 EvaluationRun 스키마 (요약)

```yaml
EvaluationRun:
  run_id: string
  world_id: string
  strategy_id: string
  stage: backtest | paper | live
  model_card_version: string | null
  risk_tier: high | medium | low
  metrics: EvaluationMetrics
  validation:
    policy_version: string
    ruleset_hash: string
    profile: backtest | paper | live
    results:              # rule_name -> RuleResult
      performance.sharpe_min: RuleResult
      robustness.dsr_min: RuleResult
    summary:
      status: pass | warn | fail
      recommended_stage: backtest_only | paper_only | paper_ok_live_candidate
      override_status: none | approved | rejected
      override_reason: string | null
      override_actor: string | null
      override_timestamp: string | null
```

### 7.2 EvaluationMetrics 스키마 (블록별 v1 필드)

```yaml
EvaluationMetrics:
  returns:
    sharpe: float                 # v1 core
    sortino_ratio: float          # v1.5+
    max_drawdown: float           # v1 core
    gain_to_pain_ratio: float     # v1 core
    var_p01: float                # v1.5+
    es_p01: float                 # v1.5+
    time_under_water_ratio: float # v1 core
    max_time_under_water_days: int  # v1.5+
  sample:
    effective_history_years: float  # v1 core
    n_trades_total: int             # v1 core
    n_trades_per_year: float        # v1 core
    regime_coverage:
      low_vol: float               # v1.5+
      mid_vol: float               # v1.5+
      high_vol: float              # v1.5+
  risk:
    factor_exposures:              # factor_name -> exposure
      mkt: float                   # v1.5+ (필요 시 'mkt'만 v1 core로 시작 가능)
      value: float                 # v1.5+
      momentum: float              # v1.5+
    incremental_var_99: float      # v1.5+
    incremental_es_99: float       # v1.5+
    adv_utilization_p95: float     # v1 core
    participation_rate_p95: float  # v1 core
    capacity_estimate_base: float  # v1.5+
  robustness:
    probabilistic_sharpe_ratio: float  # v1.5+
    deflated_sharpe_ratio: float       # v1 core
    cv_folds: int                      # v1.5+
    cv_sharpe_mean: float              # v1.5+
    cv_sharpe_std: float               # v1.5+
    sharpe_first_half: float           # v1 core
    sharpe_second_half: float          # v1 core
  diagnostics:
    strategy_complexity: float         # v1 core
    search_intensity: int              # v1 core
    returns_source: string | null      # v1 core — "explicit:strategy", "ws:derived" 등 returns 생성 출처
    validation_health:
      metric_coverage_ratio: float     # v1 core
      rules_executed_ratio: float      # v1 core
      validation_error_count: int      # v1.5+
```

### 7.3 RuleResult 스키마

```yaml
RuleResult:
  status: pass | fail | warn
  severity: blocking | soft | info
  owner: quant | risk | ops
  reason_code: string              # 예: "sample_too_small"
  reason: string                   # 사람 읽기용 메시지
  tags:
    - string                       # 예: ["sample", "tail"]
  details:
    # 추가 디버깅 정보 (임의의 key/value)
    ...: ...
```

위 스키마는 Python/Pydantic 모델 또는 유사 구조로 구현되며, 필드는 **가능한 한 backwards-compatible** 하게만 추가하는 것을 기본 원칙으로 한다.

### 7.4 Validation DSL 예제 (Tier × Stage × Profile)

아래는 risk tier, stage, validation profile 개념을 결합한 World 정책 DSL 예시다. 실제 필드 이름·값 범위는 구현 시점에 맞게 조정한다.

```yaml
risk_profile:
  tier: high
  max_capital_at_risk_pct: 2.0
  client_critical: true

validation_profiles:
  backtest:
    data_currency:
      max_lag: 5m              # v1 core
      min_history: 180d        # v1 core
    sample:
      min_effective_years: 3.0 # v1 core
      min_trades_total: 200    # v1 core
      require_high_vol_regime: true  # v1.5+
    performance:
      sharpe_min: 0.6          # v1 core
      max_dd_max: 0.30         # v1 core
      gain_to_pain_min: 1.2    # v1 core
    robustness:
      dsr_min: 0.2             # v1 core
      cv_sharpe_gap_max: 0.6   # v1.5+ (train/test gap)
      severity: soft
      owner: quant
    risk:
      incremental_var_99_max: 0.5     # v1.5+
      adv_utilization_p95_max: 0.3    # v1 core
      participation_rate_p95_max: 0.2 # v1 core

  paper:
    performance:
      sharpe_min: 0.8          # v1 core
      max_dd_max: 0.25         # v1 core
      gain_to_pain_min: 1.4    # v1 core
    robustness:
      dsr_min: 0.3             # v1 core
      cv_sharpe_gap_max: 0.4   # v1.5+
      severity: blocking
      owner: risk

  live:                         # v1.5+
    performance:
      sharpe_min: 1.0
      max_dd_max: 0.20
      gain_to_pain_min: 1.5
    risk:
      incremental_var_99_max: 0.3
      capacity_estimate_base_min: 5_000_000
    portfolio:
      max_incremental_var_99: 0.5
      min_portfolio_sharpe_uplift: 0.1

default_profile_by_stage:
  backtest_only: backtest
  paper_only: paper
  paper_ok_live_candidate: live   # v1.5+ (v1에서는 사용하지 않음)

validation:
  on_error: fail              # v1 core
  on_missing_metric: fail     # v1 core
```

이 예시는 “v1에서 현실적으로 가져갈 수 있는 최소/핵심 세트”를 그림으로 보여주는 용도이며, 실제 구현에서는 다음 원칙을 따른다.

- 필드는 가능한 한 **optional + 안전한 기본값**을 갖도록 설계한다.
- 새로운 지표·룰·프로파일을 추가할 때는, 기존 world 설정이 깨지지 않도록 **명시적 opt‑in**을 요구한다.
- risk tier / stage / profile 매핑은 world별로 튜닝 가능한 기본값을 제공하되, high‑tier + client_critical world에 대해서는 가장 보수적인 조합을 권장한다.

---

## 8. SR 11‑7 / 모델 리스크 관리 관점 매핑 (요약)

은행권 등 규제 환경에서 자주 인용되는 SR 11‑7 모델 리스크 관리 프레임워크는 검증을 대략 다음 세 축으로 나눈다.

- **개념적 건전성(conceptual soundness)**  
  - 본 문서에서는 1.1의 Model Card + risk tiering, 3장의 Rule 타입 분류, 4장의 validation/selection 역할 분리로 대응된다. 전략 아이디어/팩터의 이론적 타당성 자체는 별도 모델링 문서에서 다루되, 해당 가정·한계를 Model Card와 Evaluation Run에 연결해 추적 가능하게 한다.

- **결과 분석·백테스트/벤치마킹(outcomes analysis & benchmarking)**  
  - 2장의 Evaluation Metrics(returns/sample/risk/robustness), 3장의 PerformanceRule/RobustnessRule, 7.2의 v1 코어 지표 세트가 이 축을 담당한다. CohortRule/PortfolioRule, 벤치마크 전략(단순 Buy&Hold, cap‑weighted index, naive factor 등)을 통한 상대 비교는 결과 분석·벤치마킹 요구를 충족하는 확장 포인트다.

- **지속 모니터링(ongoing monitoring) 및 거버넌스/독립성**  
  - 5.3의 Live Monitoring, Evaluation Store·“나쁜 전략” 세트, fail‑closed(on_error/on_missing_metric) 정책과 validation_health 메트릭이 지속 모니터링 요구에 대응한다.
  - 동일 섹션에서 제안한 **독립 검증(Repo 분리, merge 권한 분리)**, override 로깅, policy 버전 관리(`validation_policy_version`·`ruleset_hash`)는 거버넌스·독립성 요건을 뒷받침한다.

이 문서와 연관된 조직/프로세스 문서에서 역할·책임(RACI), 벤치마크 모델 집합, Validation Report 템플릿만 추가로 정의하면, 소규모/중형 퀀트 운용사·브로커딜러 환경에서도 SR 11‑7 수준의 모델 검증·모니터링 체계와 구조적으로 잘 정렬된 검증 계층을 갖추게 된다.

---

## 9. 구현 갭 분석 및 주의사항 (검토 의견)

!!! warning "검토 의견"
    이 섹션은 현재 QMTL 코드베이스(2025-12-09 기준)와 본 설계 문서 간의 구조적 갭을 분석한 내용이다. 실제 구현 시 이질적으로 동작할 가능성이 높은 부분을 식별하고, 점진적 마이그레이션 전략을 제안한다.
    2025-12-13 기준 v1.5 closeout으로 주요 갭은 해소되었으며, 일부 항목은 “추가 고도화/조직 프로세스” 성격으로 남아 있다.

### 9.1 Validation 레이어 위치 문제

**현재 구현:**

```
Runner.submit() → (SDK metrics precheck) → Gateway /worlds/{world_id}/evaluate → WorldService.evaluate()
```

- `ValidationPipeline`은 **SDK/Runtime 레이어**(`qmtl/runtime/sdk/validation_pipeline.py`)에 위치하지만, **metrics-only(precheck)** 로 축소됨
- `policy_engine.py`는 **WorldService 하위**에서만 사용되며, Runner/SDK에서 직접 import하지 않음
- 정책/룰 실행·오케스트레이션은 WorldService가 담당(SSOT)

**본 설계 제안:**

- WorldService가 검증의 **SSOT**
- Rule 세트를 WS가 관리하고, Runner는 메트릭만 계산해서 전달
- `validation` 블록이 정책 DSL의 일부로 WS에서 파싱/실행

**갭:**

- Runner/SDK에는 여전히 "로컬 precheck" 개념이 남아 있으나, 이는 **참고용(metrics 산출 결과)** 이고 SSOT가 아님
- 설계처럼 "WS가 Rule 파이프라인 전체를 오케스트레이션"하려면, SDK 출력(메트릭/시계열/컨텍스트)과 WS 입력 스키마/계약을 더 명확히 고정할 필요가 있음

**권장 마이그레이션:**

1. 단기: SDK ValidationPipeline을 metrics-only로 유지하고, WS `/evaluate` 계약(입력/출력/저장 메타)을 통합 테스트로 고정
2. 중기: WS가 Rule 실행·요약 산출·EvaluationRun 저장을 단일 진입으로 일원화(SSOT 강화)
3. 장기: SDK의 ValidationPipeline(로컬 precheck) 디프리케이션/제거 및 문서/런북 정리

**현 상태(2025-12-13):**

- SDK→WS `/evaluate` 경로의 계약(리스크 메트릭 전달/에러 매핑 등)을 테스트로 고정: `tests/qmtl/runtime/sdk/test_worldservice_eval_contract.py`
- 디프리케이션 가이드(ko/en): `docs/ko/guides/sdk_deprecation.md`, `docs/en/guides/sdk_deprecation.md`

---

### 9.2 메트릭 스키마 확장성

**현재 구현 (`PerformanceMetrics` in validation_pipeline.py):**

```python
@dataclass
class PerformanceMetrics:
    sharpe: float = 0.0
    max_drawdown: float = 0.0
    win_ratio: float = 0.0
    profit_factor: float = 0.0
    # ... 고정된 필드들
```

**본 설계 제안:**

```yaml
EvaluationMetrics:
  returns: { sharpe, var_p01, es_p01, ... }
  sample: { effective_history_years, n_trades_total, ... }
  risk: { factor_exposures, incremental_var_99, ... }
  robustness: { dsr, cv_sharpe_mean, ... }
  diagnostics: { extra_metrics: {...} }  # 확장 슬롯
```

**갭:**

- 현재 메트릭은 **flat한 dataclass**로, 블록별 구조화 없음
- `diagnostics.extra_metrics` 같은 **확장 슬롯** 미존재
- 새 지표 추가 시 dataclass 수정 필요 (OCP 위반 가능성)

**권장 마이그레이션:**

1. 기존 `PerformanceMetrics`에 `extra_metrics: Dict[str, Any] = field(default_factory=dict)` 필드 추가
2. 점진적으로 블록별 서브모델(`ReturnsMetrics`, `SampleMetrics` 등) 도입
3. 기존 flat 필드를 deprecated alias로 유지하며 하위 호환성 확보

---

### 9.3 Policy DSL 구조

**현재 `Policy` 모델 (policy_engine.py):**

```python
class Policy(BaseModel):
    thresholds: dict[str, ThresholdRule] = ...
    top_k: TopKRule | None = ...
    correlation: CorrelationRule | None = ...
    hysteresis: HysteresisRule | None = ...
```

**본 설계 제안:**

```yaml
validation:
  data_currency: { max_lag, min_history }
  sample: { min_effective_years, min_trades_total }
  performance: { sharpe_min, max_dd_max }
  robustness: { dsr_min, severity: soft }
  risk: { incremental_var_99_max }
selection:
  gates/score/topk/constraints/hysteresis
```

**갭:**

- 현재는 `validation` vs `selection` 분리가 없음
- `severity: blocking|soft|info`, `owner: quant|risk|ops` 메타데이터 미지원
- 레이어별(Data/Sample/Performance/Risk/Robustness) 구조화 없음

**권장 마이그레이션:**

1. 현재 `thresholds`를 `selection.thresholds`로 alias 처리
2. 새로운 `validation` 블록을 optional로 추가
3. migration 기간(예: 2 릴리스) 후 구 스키마 deprecated 경고
4. 기존 world policy 파일에 대한 자동 변환 스크립트 제공

---

### 9.4 Rule 모듈성과 RuleResult

**현재 구현:**

- `_apply_thresholds()`, `_apply_topk()` 등 **함수 기반** (Rule 객체 아님)
- 결과는 단순히 `List[str]` (통과한 strategy ID 목록)
- 실패 사유, severity, owner 등 메타데이터 없음

**본 설계 제안:**

```python
class ValidationRule(Protocol):
    name: str
    def evaluate(self, metrics, context) -> RuleResult: ...

class RuleResult(BaseModel):
    status: Literal["pass", "fail", "warn"]
    severity: Literal["blocking", "soft", "info"]
    owner: Literal["quant", "risk", "ops"]
    reason_code: str
    reason: str
    details: dict
```

**갭:**

- Rule 단위 추적 불가 → "왜 떨어졌는지" 설명하기 어려움
- fail-closed 정책, 경고 모드 운영 불가

**권장 마이그레이션:**

1. 기존 함수들을 **Rule 클래스로 래핑**하는 adapter 패턴 사용
2. `evaluate_policy()` 반환 타입을 `List[str]` → `PolicyEvaluationResult` 확장
   - `PolicyEvaluationResult`: selected IDs + `Dict[str, RuleResult]` 맵 포함
3. 기존 호출자는 `.selected_ids` 속성으로 하위 호환 유지

---

### 9.5 Evaluation Run 모델

**현재 구현:**

- `ActivationEntry`, `ValidationCacheEntry` 등 **단편적인 저장 모델**
- 명시적인 **Evaluation Run** 개념 미존재
- 정책 버전, ruleset hash, model card 등 추적 메타데이터 없음

**본 설계 제안:**

- `EvaluationRun`: `(world_id, strategy_id, run_id)` 키로 전체 평가 이력 관리
- `validation.policy_version`, `ruleset_hash`, `recommended_stage` 포함

**갭:**

- "이 전략이 어떤 정책 버전 아래 어떤 룰로 통과/실패했는지" 추적 불가
- 정책 변경 전후 diff 시뮬레이션 불가

**권장 마이그레이션:**

1. 기존 `ValidationCacheEntry`를 `EvaluationRun`의 서브셋으로 취급
2. WS storage layer에 `evaluation_runs` 테이블/컬렉션 추가
3. 기존 API는 내부적으로 EvaluationRun을 생성하되, 응답 스키마는 점진적으로 확장

---

### 9.6 CohortRule / PortfolioRule / StressRule

**현재 구현:**

- 단일 전략 단위 평가만 지원
- 캠페인(다중 전략 동시 제출) 개념 없음
- 포트폴리오 레벨 incremental risk 평가 없음

**본 설계 제안:**

- `CohortRule`: 여러 전략을 함께 평가해 다중 테스트 통제
- `PortfolioRule`: 기존 live 전략과 합쳐서 incremental VaR/ES 계산
- `StressRule`: 사전 정의된 시나리오별 재시뮬레이션

**갭:**

- 현재 아키텍처에서 이 개념들을 도입하려면 **상당한 확장** 필요
- WS가 "활성 전략 목록"을 알고 있어야 portfolio-level 평가 가능

**권장 마이그레이션:**

1. v1에서는 CohortRule/PortfolioRule/StressRule을 **optional extension**으로 분류
2. 먼저 단일 전략 Rule 체계를 안정화
3. 이후 WS에 "active portfolio snapshot" 개념 도입 후 portfolio-level rule 추가

---

### 9.7 구현 우선순위 제안

| Phase | 범위 | 기존 코드 영향 | 예상 공수 |
|-------|------|----------------|-----------|
| **P1** | EvaluationMetrics 블록 구조화 + `extra_metrics` 확장 슬롯 | 낮음 (additive) | 1–2일 |
| **P2** | RuleResult 스키마 도입 + 기존 함수들 Rule 래핑 | 중간 (adapter) | 3–5일 |
| **P3** | Policy DSL에 `validation` 블록 추가 (selection과 분리) | 중간 (migration) | 3–5일 |
| **P4** | EvaluationRun 모델 + policy_version/ruleset_hash 추적 | 높음 (storage 변경) | 5–7일 |
| **P5** | Cohort/Portfolio/StressRule | 높음 (새 기능) | 7–14일 |

---

### 9.8 핵심 설계 결정 필요 사항

본 설계를 구현하기 전에 다음 사항에 대한 명시적 결정이 필요하다:

1. **검증 오케스트레이션 위치**  
   SDK(`ValidationPipeline`)에서 계속할지, WS로 이전할지?  
   → 현실적으로는 **하이브리드 접근**(SDK가 Rule 실행, WS가 결과 저장/정책 관리)이 마이그레이션 비용을 낮출 수 있다.

2. **기존 Policy 스키마 호환성**  
   마이그레이션 기간과 deprecated 정책은?  
   → 최소 2 릴리스 동안 구 스키마 지원 권장.

3. **fail-closed 기본값 적용 시점**  
   프로덕션 적용 시점과 티어별 다른 정책?  
   → `tier: high` world부터 단계적 적용, `tier: low`는 opt-in 방식 권장.

4. **Rule 소유권 분리**  
   `owner: quant|risk|ops` 메타데이터를 실제 권한 시스템과 어떻게 연결할지?  
   → 초기에는 정보성 태그로만 사용, 이후 CI/approval workflow와 연동.

5. **스트리밍 아키텍처와의 정렬**  
   QMTL은 기본적으로 WorldService/Gateway/SDK가 **스트리밍 이벤트(ActivationUpdated, QueueUpdated, Commit Log 등)** 를 중심으로 동작한다. 검증 계층 구현 시에도 다음 원칙을 고려해야 한다.
   - EvaluationRun과 validation 결과는 단발성 batch 산출물이 아니라, **시간에 따라 누적·갱신되는 스트림의 스냅샷**으로 취급한다.
   - Runner.submit 경로에서 모든 검증을 동기적으로 처리하려 하지 말고,  
     - “필수 최소 검증”만 submit 파이프라인 안에서 수행하고,  
     - 나머지 심층 검증/캠페인/Cohort/Portfolio/Stress 룰은 **별도 스트리밍/배치 파이프라인**에서 EvaluationRun 스트림을 소비하는 형태로 분리한다.
   - WorldService는 ControlBus/Commit Log 등 기존 이벤트 버스를 활용해  
     - `EvaluationRunCreated`/`EvaluationRunUpdated`/`ValidationProfileChanged` 같은 이벤트를 발행하고,  
     - 검증/리포트/모니터링 컴포넌트는 이를 구독하여 **비동기적으로 Rule을 실행**하도록 설계하는 것이 QMTL의 스트리밍 모델과 더 자연스럽게 맞는다.
   - Core Loop E2E 경로와는 별도로, **검증 결과/상태를 스트리밍 대시보드(예: Prometheus/Grafana, Web UI)** 쪽으로 지속적으로 흘려보내는 것을 전제로 설계해야 한다.  
     Runner/CLI가 “현재 검증 상태/추천 단계”를 조회할 때도 WS의 EvaluationRun 스냅샷을 읽는 대신, 스트림 기반 상태 저장소(캐시/뷰)를 조회하는 구조가 장기적으로 더 일관성 있다.

---

## 10. 품질 목표 및 SLO (초안)

검증 계층이 “어느 정도까지 잘 작동하면 성공으로 볼 것인지”를 정량화하기 위해, 다음과 같은 품질 목표·SLO를 초안 수준으로 제안한다. 실제 수치는 조직/World별로 조정 가능하며, 본 문서는 지표 구조만 고정한다.

### 10.1 기능적 목표 (Validation Effectiveness)

- **False‑negative 제한 (고위험 World)**  
  - `risk_profile.tier=high` 및 `client_critical=true`인 World에 대해,  
    과거 실패 사례 유형(예: 과도한 레버리지, 극단적 DD, 유동성 붕괴)에 해당하는 synthetic 전략/히스토리를 재현했을 때:
    - 최소 95% 이상의 테스트 케이스에서 하나 이상의 Rule이 `status=fail` 또는 `status=warn`를 반환해야 한다.
- **Coverage 목표**  
  - v1 코어 메트릭 세트에 대해 `validation_health.metric_coverage_ratio >= 0.98`를 유지하는 것을 목표로 한다.

### 10.2 운영 목표 (Pipeline Reliability)

- **단건 EvaluationRun 처리 지연**  
  - p95 latency < 1초, p99 latency < 5초 (단일 World/전략 EvaluationRun 기준, v1 코어 룰 세트만 적용한 경우).
- **에러/누락 이벤트 비율**  
  - `validation.on_error in {fail,warn}` 또는 `on_missing_metric in {fail,warn}` 로 기록된 이벤트 비율이 전체 EvaluationRun의 X% 이하(예: 1% 이하)를 유지하도록 한다.

### 10.3 리스크 관점 목표 (Ex‑post 실패율)

- **검증 허용 후 ex‑post 실패 비율**  
  - “검증 계층이 허용(passed)했으나, ex‑post 관점에서 명백히 피했어야 할 실패 케이스”로 분류된 live 전략 비율을  
    - 연간 전체 live 전략 수의 Y% 이하(예: 2% 이하)로 유지하는 것을 목표로 한다.
- 해당 지표는 Model Risk Management 문서(`model_risk_management_framework.md`)와 연동해 관리하며,  
  검증 계층 개선의 우선순위를 정하는 기준으로 사용한다.

---

## 11. 검증 계층 테스트 전략 (초안)

검증 계층은 일반 유닛 테스트 외에도 **정책/룰 변경이 기존 World/전략에 미치는 영향**을 검증할 수 있는 테스트 전략이 필요하다. 아래는 이를 위한 최소 구성 초안이다.

### 11.1 단위 테스트 (Rule‑level)

- 각 ValidationRule에 대해:
  - 정상 입력에서 기대한 `status`/`reason_code`/`severity`가 나오는지 검증.
  - 필수 메트릭 누락/에러 발생 시 `on_error`/`on_missing_metric` 정책을 준수하는지 확인.

### 11.2 시나리오 테스트 (Good/Bad/Borderline 전략)

- 대표적인 전략 샘플 또는 EvaluationRun 스냅샷 세트를 정의한다.
  - Good: 안정적 Sharpe, 적절한 샘플, tail·유동성 리스크 양호.
  - Bad: 극단적 레버리지, 지나치게 짧은 백테스트, 과도한 탐색 강도 등.
  - Borderline: 기준 근처에 위치한 전략들.
- 정책/룰 변경 시:
  - 각 샘플에 대해 어떤 RuleResult가 발생하는지 자동으로 비교·리포트한다.

### 11.3 회귀 테스트 (Policy Diff)

- `validation_policy_version`/`ruleset_hash` 변경 시, 과거 N개월(예: 12개월)의 EvaluationRun 히스토리에 대해:
  - 이전 정책 vs 새로운 정책을 적용했을 때의 `summary.status`·`recommended_stage` diff를 계산.
  - 영향 범위가 특정 임계값(예: 전체 Run의 5% 초과)을 넘으면 경고 및 수동 검토를 요구한다.

### 11.4 성능/부하 테스트

!!! note "릴리즈 버전 확정 시점에 수행"
    성능/부하 테스트는 릴리즈 버전(예: v1.6/v2.0) 범위와 목표 SLO가 확정되는 시점에 벤치마크 환경·부하 모델·CI 게이트를 고정하고 별도 작업으로 수행한다.

- 다양한 World/전략 조합, 동시 EvaluationRun 수(N) 시나리오에 대해:
  - Rule 평가 latency, 에러율, 스트림 처리 지연을 측정.
  - 10.2에서 정의한 SLO를 만족하는지 확인.

---

## 12. 시스템 인바리언트 및 안전장치 (초안)

운영/리스크 관점에서 “절대로 깨져서는 안 되는 조건”을 명시해 두면, 코드/구성 변경 시 검증·테스트의 기준이 명확해진다. 아래 인바리언트는 초안이며, 실제 적용 시 World tier 등에 따라 확장될 수 있다.

### 12.1 실행 단계 관련 인바리언트

- **Invariant 1 — live 단계 정합성**
  - `stage=live` 또는 `effective_mode=live`인 전략에 대해서는:
    - 최신 EvaluationRun의 `summary.status`가 반드시 `"pass"` 여야 한다.
    - 최신 EvaluationRun의 `validation.policy_version`은 해당 World의 현재 WorldPolicy 버전과 호환되어야 한다(최소 버전 이상).

### 12.2 고위험 World에 대한 강제 규칙

- **Invariant 2 — high‑tier World의 fail‑closed 정책**
  - `risk_profile.tier=high` 및 `client_critical=true`인 World에서는:
    - `validation.on_error`와 `validation.on_missing_metric`은 항상 `"fail"`이어야 한다.
    - 이 설정을 완화하려면 별도 승인 플로우 및 Change Log 기록이 필요하다.

### 12.3 Override 관련 인바리언트

- **Invariant 3 — override 관리**
  - `override_status=approved`인 EvaluationRun(또는 전략/World 조합)은:
    - 별도 목록으로 집계되어야 하며,
    - 설정된 기간(예: 30일/90일) 내에 반드시 재검토 대상이 되어야 한다.
  - Override 승인 시:
    - `override_reason`, `override_actor`, `override_timestamp`는 필수 기록 필드다.

이러한 인바리언트는 Core Loop E2E 테스트, CI 정책 체크, 운영 점검(checklist) 등에 반영되는 것을 전제로 한다.

---

## 13. E2E 시나리오 예제 (개략)

검증 계층이 실제 QMTL Core Loop와 어떻게 상호작용하는지 이해를 돕기 위해, 대표적인 세 가지 흐름을 개략적으로 정리한다.

### 13.1 새 전략의 최초 backtest 제출

1. 개발자는 Model Card를 작성하고, 전략 코드를 준비한다.
2. `Runner.submit(MyStrategy, world="demo")` 호출:
   - SDK가 히스토리 warmup → backtest → returns/metrics 추출.
   - WorldService에 EvaluationRun이 생성되고, v1 코어 validation 프로파일이 적용된다.
3. ValidationRule들이 EvaluationMetrics를 평가하여 `RuleResult` 집합과 `summary.status`/`recommended_stage`를 생성한다.
4. SDK/CLI는 SubmitResult에 `evaluation_run_id`/`summary` 일부를 매핑해 사용자에게 보여준다.
5. Risk/Validator는 Evaluation Store와 Model Card를 기반으로 Validation Report 초안을 작성한다.

### 13.2 paper까지 승격되는 경우

1. 여러 번의 backtest EvaluationRun에서 일관되게 `recommended_stage=paper_only` 또는 `paper_ok_live_candidate`가 나온다.
2. Risk/Validator가 Validation Report를 승인하고, WorldPolicy에서 해당 전략/World에 대해 paper 프로파일을 활성화한다.
3. PM/Ops가 합의 후, `/worlds/{id}/apply` 또는 CLI를 통해 paper 모드 실행을 허용한다.
4. 이후 EvaluationRun은 paper 프로파일을 사용해 검증되며, Live Monitoring 지표(최근 30/60/90일 결과)가 누적된다.

### 13.3 live 전략의 성능 악화로 인한 demotion

1. live 전략에 대해 주기적으로 Live EvaluationRun이 생성되고, backtest 대비 성능 decay 및 risk breach가 감지된다.
2. Live Monitoring 규칙에 따라:
   - 특정 임계값을 초과하면 해당 전략은 자동 demotion 후보로 태깅된다.
3. Risk/Ops/PM은 Validation Report 업데이트와 함께 전략 상태를 검토하고,
   - `/apply` 플로우를 통해 `effective_mode`를 paper 또는 backtest로 강등하거나,
   - override가 필요한 경우 `override_status=approved`로 승인하되, Invariant 3에 따라 재검토 일정과 사유를 기록한다.

위 시나리오는 상세한 API/타임라인을 생략한 개략이며, 실제 구현 시에는 Core Loop 시퀀스 다이어그램 및 WorldService API 문서와 함께 보완된다.

이러한 결정들을 먼저 정리한 후 구현에 들어가면, 설계와 실제 동작 사이의 이질성을 최소화할 수 있다.
