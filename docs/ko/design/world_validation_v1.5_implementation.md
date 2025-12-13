# World 검증 v1.5 진행 현황 및 잔여 작업

본 문서는 `world_validation_architecture.md`·`world_validation_v1_implementation_plan.md`의 v1.5 범위를 closeout하기 위해 **현재 구현 상태**를 정리하고, v1.5 이후의 **후속(선택) 확장 과제**를 분리해 두는 체크포인트다.

## 진행 현황 (요약)
- **핵심 검증 경로**: EvaluationRun/metrics 블록, RuleResult 메타(severity/owner/tags), validation_profiles(backtest/paper), recommended_stage·policy_version·ruleset_hash 저장까지 구현 완료.
- **확장 레이어**: cohort/portfolio/stress/live 평가·append-only 기록, risk hub 스냅샷 소비/베이스라인 파생치, ControlBus 소비자(dedupe 포함) 연동, TTL(10s)·hash(sha256)·actor 헤더 강제.
- **Blob/offload**: redis/file/s3 BlobStore 팩토리 제공, redis TTL 기본 10초, covariance offload 기준 적용.
- **게이트웨이 생산자**: 리밸런스 경로에서 risk hub 스냅샷 push(+offload) 적용, RiskHubClient가 TTL/actor 헤더를 포함하도록 보강.
- **회귀/도구**: `scripts/policy_diff_batch.py` 추가로 정책 변경 영향 리포트 CI/배치 실행 가능, extended validation 워커 부하 시나리오 테스트 추가.
- **문서/내비게이션**: Risk Signal Hub/Exit Engine 문서를 mkdocs nav에 추가.
- **품질**: 풀 CI 스위트, mypy, mkdocs, 링크/사이클 검사 모두 통과.

## 아키텍처 만족도 매트릭스 (2025-12-13 기준)

아래 표는 `world_validation_architecture.md`의 핵심 요구를 기준으로 “현재 코드베이스가 어디까지 충족하는지”를 요약한 매트릭스입니다.

- **closeout 상태**
  - 2025-12-13 기준, 본 문서의 매트릭스 항목은 모두 **충족** 상태이며 잔여 갭 트래킹(#1927)을 종료합니다.

- **상태 정의**
  - **충족**: 설계 의도를 v1.5 범위에서 구현·테스트/문서까지 완료
  - **부분**: 핵심은 구현했지만, 설계에서 명시한 일부 조건/운영 패키지/자동화가 빠짐
  - **미구현**: 설계에서 요구하지만 아직 코드/운영 경로가 없음

| 설계 섹션 | 요구(요약) | 상태 | 구현 근거(대표) | 남은 갭 / 후속(G*) |
| --- | --- | --- | --- | --- |
| §1 원칙 | WS가 검증 SSOT, 레이어드 검증 | 충족 | `qmtl/services/worldservice/services.py`, `qmtl/services/worldservice/policy_engine.py` | - |
| §2 Metrics 블록 | returns/sample/risk/robustness/diagnostics + 확장 슬롯 | 충족 | `qmtl/runtime/sdk/world_validation_metrics.py`, `qmtl/services/worldservice/schemas.py` | - |
| §3 Rule 모듈성 | RuleResult(status/severity/owner/reason/details) | 충족 | `qmtl/services/worldservice/policy_engine.py` | - |
| §4 DSL 구조 | validation vs selection, profiles, recommended_stage | 충족 | `qmtl/services/worldservice/policy_engine.py` | - |
| §4/5 저장 | EvaluationRun에 policy_version/ruleset_hash/override 추적 | 충족 | `qmtl/services/worldservice/storage`, `qmtl/services/worldservice/services.py` | - |
| §5 피드백 루프 | policy diff/회귀 자동화 도구 | 충족 | `scripts/policy_diff_batch.py`, `.github/workflows/policy-diff-regression.yml`, `operations/policy_diff/bad_strategies_runs` | - |
| §5.3 Live Monitoring | live 결과 상시 재검증(run/report) | 충족 | `qmtl/services/worldservice/routers/live_monitoring.py`, `qmtl/services/worldservice/live_monitoring_worker.py`, `scripts/live_monitoring_worker.py`, `scripts/generate_live_monitoring_report.py` | - |
| §5.3 Fail-closed | on_error/on_missing_metric 기본값/강제 | 충족 | `qmtl/services/worldservice/policy_engine.py`, `qmtl/services/worldservice/decision.py` | - |
| §5.3 Evaluation Store | append-only 보존/운영 가이드 | 충족 | `docs/ko/operations/evaluation_store.md`, `scripts/purge_evaluation_run_history.py`, `.github/workflows/evaluation-store-retention.yml` | - |
| §5.3 Validation Report | 표준 리포트 산출물/보관 | 충족 | `scripts/generate_validation_report.py`, `docs/ko/operations/validation_report.md` | - |
| §8/§12 Invariants | SR 11-7 인바리언트 점검 API | 충족 | `qmtl/services/worldservice/routers/validations.py`, `qmtl/services/worldservice/validation_checks.py`, `scripts/generate_override_rereview_report.py`, `docs/ko/operations/world_validation_governance.md` | - |
| §10 SLO/관측성 | 핵심 SLO/알람/대시보드 표준화 | 충족 | `alert_rules.yml`, `docs/ko/operations/world_validation_observability.md`, `operations/monitoring/world_validation_v1.jsonnet` | - |
| 스트리밍 정착 | ControlBus/큐 토픽·그룹·재시도·DLQ 표준화 | 충족 | `docs/ko/operations/controlbus_queue_standards.md`, `qmtl/services/worldservice/controlbus_*`, `qmtl/services/dagmanager/controlbus_producer.py`, `qmtl/services/gateway/controlbus_ack.py` | - |

## 후속(선택)

본 문서의 매트릭스가 모두 **충족** 상태가 되면서(v1.5 closeout), 아래 항목은 v1.5 이후 확장 과제로 분리합니다.

추적 이슈: #1934

- **Live 모니터링 자동 생성**: #1907 (완료)
- **Portfolio/Stress 입력 소스 강화**: #1909 (완료)
- **SDK→WS SSOT 전환**: #1910 (완료)
- **거버넌스/운영 가시성**: #1911 (완료)

## 최근 진행 업데이트
- v1 코어 risk 메트릭 산출 보강: #1922
- Policy diff 회귀 자동화 운영 정착(CI/크론 + bad strategies 세트): #1923
- Evaluation Store retention 정책 코드/잡 고정: #1924
- World Validation 관측성(알람/대시보드 튜닝 + 운영 증빙): #1925
- ControlBus 표준 템플릿 전면 적용 + 리허설/증빙: #1926

아래 섹션은 운영 참고/템플릿 성격이며, v1.5 DoD에 포함되지 않는 후속 작업도 포함합니다.

- ControlBus 경로 dedupe/TTL 계측: `risk_hub_snapshot_dedupe_total{world_id,stage}`·`risk_hub_snapshot_expired_total{world_id,stage}` 추가, 소비자에서 stage-aware 집계.
- Stage 헤더 전파: gateway 리밸런스→RiskHubClient `X-Stage` 전달, activation 스냅샷도 `stage=live` 부여, WS 라우터가 provenance.stage 기록.
- 런북/알림: ko/en Risk Signal Hub 런북에 헤더/TTL/dedupe 대응 추가, Alertmanager 룰에 dedupe/expired 스파이크 감지 룰 포함.
- 회귀 자동화(G3): `scripts/policy_diff_batch.py`가 stage 지정(`--stage`)과 runs 디렉터리 glob(`--runs-dir/--runs-pattern`)를 지원하여 “나쁜 전략” 세트+최신 runs를 묶어 크론/CI에서 임팩트 비율 임계(`--fail-impact-ratio`)로 실패 플래그를 낼 수 있음.

## G3 실행 가이드 (회귀/스토어)
- “나쁜 전략” 세트: `operations/policy_diff/bad_strategies_runs/*.json`
- 크론/CI 스니펫: `uv run -m scripts.policy_diff_batch --old baseline.yml --new candidate.yml --runs-dir operations/policy_diff/bad_strategies_runs --runs-pattern '*.json' --stage backtest --output policy_diff_report.json --fail-impact-ratio 0.05`
- GitHub Actions: `.github/workflows/policy-diff-regression.yml` (리포트 아티팩트 업로드 + 임계 초과 시 실패)
- 스토어/보존: `scripts/purge_evaluation_run_history.py`, `.github/workflows/evaluation-store-retention.yml` (history 180d 권장)

## G5 전환 스텝 (SDK→WS)
- SDK: ValidationPipeline은 **metrics 산출(precheck)** 만 담당하고, 정책/룰 실행·오케스트레이션은 WS `/evaluate` 단일 진입으로 수렴(SSOT).
- 전환: `Runner.submit` 기본 경로에서 WS 평가 결과를 신뢰하고, 로컬 precheck는 참고 정보로만 노출한다.
- 롤백/우회(긴급): WS 장애/변경 대응 시 `Runner.submit(..., auto_validate=False)`로 제출/런 생성만 수행하거나, 문제 버전 전 SDK pin으로 복구한다.

## G5 전환 체크리스트 (추가)
- [ ] WS 통합 테스트: 룰 실행/오류 처리/오프로드 경로를 WS 단일 진입으로 검증.
- [ ] SDK 디프리케이션 가이드: precheck/WS SSOT 관계 명시, 로컬 정책 평가 제거 사실 및 제거 일정/대체 경로 명시.
- [ ] 모드별(Backtest/Paper/Live) WS 오케스트레이션 플래그 롤아웃 순서 합의 및 알림.

### 모드별 롤아웃 가이드
- Backtest → Paper → Live 순으로 단계 적용, 각 단계에서 수집/재시도율/알람을 모니터링 후 다음 단계 진행.
- 롤백: 특정 스테이지에서 문제 발생 시 `auto_validate=False` 우회 또는 SDK 버전 pin으로 즉시 복구하고 WS 로그/메트릭으로 원인 파악.
- 커뮤니케이션: 롤아웃 전/후 changelog+런북 업데이트, 제출/파이프라인 소유자 대상 공지.

## 리허설/검증 시나리오 (필수)
- 큐/워커: 중복 메시지, 재시도 백오프, DLQ 전송, TTL 만료 후 처리 거부, dedupe hit/미스 메트릭.
- Risk snapshot: TTL 10s 초과, 해시 불일치, actor 누락, 가중치 합≠1, offload 기준 위반 시 거부·알림.
- Live 스케줄러: 잡 미실행/지연/워커 실패 알람 트리거, decay 계산 오류 처리.
- Evaluation Store: 이력 조회/override 적용/정책 버전 추적 쿼리 정상 동작.
- 회귀 배치: “나쁜 전략” 세트에서 정책 변경 시 임계 초과 실패 플래그 확인.

## 작업 배정 템플릿 (작성용)
| 갭 | 담당 | 마감 | PR/문서 링크 | 증빙 링크(로그/알람/대시보드/샘플) |
| --- | --- | --- | --- | --- |
| G1 ControlBus 표준화 |  |  |  |  |
| G2 Live 모니터링 |  |  |  |  |
| G3 Evaluation Store·회귀 |  |  |  |  |
| G4 Portfolio/Stress 입력 |  |  |  |  |
| G5 SDK→WS 전환 |  |  |  |  |
| G6 거버넌스/가시성 |  |  |  |  |

## 주간 리포트 포맷 (채워서 공유)
- 진행: 이번 주 완료 항목(체크리스트 참조)과 주요 증빙 링크.
- 리스크/차단: 의존 서비스, 인프라, 권한, 설계 결정 대기 등.
- 다음 주 계획: 체크리스트 중 이어서 진행할 항목, 추가 리허설 필요 리스트.
- 의사결정 요청: SLA·임계값·스키마 변경 등 합의가 필요한 사항.

## 참고 링크
- 설계: [world_validation_architecture.md](world_validation_architecture.md)
- v1 계획: [world_validation_v1_implementation_plan.md](world_validation_v1_implementation_plan.md)
- Risk Hub 설계: [risk_signal_hub.md](risk_signal_hub.md)
- 운영 런북: [../operations/risk_signal_hub_runbook.md](../operations/risk_signal_hub_runbook.md)
