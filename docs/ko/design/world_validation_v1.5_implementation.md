# World 검증 v1.5 진행 현황 및 잔여 작업

본 문서는 `world_validation_architecture.md`·`world_validation_v1_implementation_plan.md`의 v1.5 범위를 마무리하기 위해 **현재 구현 상태**와 **남은 작업**을 정리한 체크포인트다.

## 진행 현황 (요약)
- **핵심 검증 경로**: EvaluationRun/metrics 블록, RuleResult 메타(severity/owner/tags), validation_profiles(backtest/paper), recommended_stage·policy_version·ruleset_hash 저장까지 구현 완료.
- **확장 레이어**: cohort/portfolio/stress/live 평가·append-only 기록, risk hub 스냅샷 소비/베이스라인 파생치, ControlBus 소비자(dedupe 포함) 연동, TTL(10s)·hash(sha256)·actor 헤더 강제.
- **Blob/offload**: redis/file/s3 BlobStore 팩토리 제공, redis TTL 기본 10초, covariance offload 기준 적용.
- **게이트웨이 생산자**: 리밸런스 경로에서 risk hub 스냅샷 push(+offload) 적용, RiskHubClient가 TTL/actor 헤더를 포함하도록 보강.
- **회귀/도구**: `scripts/policy_diff_batch.py` 추가로 정책 변경 영향 리포트 CI/배치 실행 가능, extended validation 워커 부하 시나리오 테스트 추가.
- **문서/내비게이션**: Risk Signal Hub/Exit Engine 문서를 mkdocs nav에 추가.
- **품질**: 풀 CI 스위트, mypy, mkdocs, 링크/사이클 검사 모두 통과.

## 남은 주요 갭
1) **스트리밍·운영 배포 정착**
   - ControlBus/큐 → ExtendedValidation/라이브·스트레스 워커를 운영 스케일에서 idempotent하게 트리거하도록 토픽/그룹/재시도·DLQ·헬스 메트릭을 표준화해야 함.
   - risk snapshot 프로듀서(gateway/리스크 엔진) 측 재시도·알람·dedupe 키 규칙 문서화/코드 반영 필요.

2) **Live 모니터링 자동 생성**
   - 주기적 Live EvaluationRun 생산(30/60/90일 realized Sharpe/DD/ES, decay 지표)을 스케줄러/워커로 운영 경로에 연결해야 함.
   - 라이브 리포트 템플릿/노출 경로 정의 필요.

3) **Evaluation Store & 회귀 자동화**
   - EvaluationRun/override/정책 버전 히스토리를 불변 스토어로 관리하는 정책 명문화.
   - “나쁜 전략” 회귀 세트 + `scripts/policy_diff.py`를 주기 배치/CI 옵션으로 연결하고, 영향 임계치 초과 시 경고/실패 플래그화.

4) **Portfolio/Stress 입력 소스 강화**
   - realized_returns_ref/stress ref를 생성하는 프로듀서(gateway/리스크 엔진) 연결과 해시 검증/ACL 경로를 표준화.
   - risk hub 스냅샷 계약(가중치 합≈1, TTL, hash, actor, offload 기준) 검증을 프로듀서에도 강제.

5) **SDK 얇게 만들기 & WS SSOT 전환**
   - Runner ValidationPipeline을 metrics-only로 축소하고, 룰 실행·오케스트레이션을 WS 단일 진입으로 이관하는 단계적 플랜 필요.

6) **거버넌스/운영 가시성**
   - 독립 검증(Repo/권한 분리), override 재검토 큐, SR 11-7 인바리언트 운영 체크/대시보드 정착.
   - risk hub freshness/누락, extended validation 워커 성공/실패 메트릭 + Alertmanager 룰 보완.

## 다음 실행 우선순위 제안
1. ControlBus/큐 운영 패키징: 토픽·그룹·재시도/백오프·DLQ·헬스 메트릭 템플릿 확정 후 워커/프로듀서에 적용.
2. Live 모니터링 스케줄러 배포: live run 생성 워커 + 리포트 경로 연결, 기본 주기/타임아웃 정의.
3. Policy diff 회귀 배치: “나쁜 전략” 샘플 세트 마련 → `scripts/policy_diff.py` 크론/CI 옵션화 → 영향 임계 플래그 도입.
4. realized/stress 프로듀서 연결: gateway/리스크 엔진에서 realized_returns_ref·stress ref를 hub로 push, 해시/actor 검증 강제.
5. SDK→WS 오케스트레이션 전환 계획 수립: ValidationPipeline 축소, WS 룰 실행/오류 처리 중심으로 마이그레이션 단계 정의.
6. 운영 가시성: risk hub freshness, extended validation 성공률, snapshot dedupe hit 등 메트릭 노출 + Alertmanager 룰 추가.

## 갭별 상세 실행 계획
- G1 ControlBus/큐 운영 표준화
  - 토픽/컨슈머 그룹/재시도·DLQ·백오프·idempotency 키 템플릿 정의 → gateway·ExtendedValidation 워커·RiskHub 컨슈머에 공통 적용.
  - dedupe 키 규칙(스냅샷 해시+actor+stage), 재시도/알람 정책을 프로듀서 코드와 운영 문서에 반영.
  - 헬스 메트릭(큐 적체, 재시도·DLQ 카운트, dedupe hit, 처리 지연)과 Alertmanager 룰 초안 배포.
  - DoD: 템플릿이 코드/런북에 반영되고, 재처리·중복 시나리오 리허설 로그/메트릭이 확보.

- G2 Live 모니터링 자동 생성
  - 스케줄러(30/60/90일) → Live EvaluationRun 생성 워커 연결, decay 지표 계산 파이프라인을 metrics-only 경로로 연결.
  - 라이브 리포트 템플릿(요약·추세·임계 경고) 정의, 노출 경로(대시보드/API) 확정 및 샘플 출력 검증.
  - 지연/실패 알림(스케줄 미실행, 워커 실패, 지표 계산 에러) 룰 추가.
  - DoD: 정해진 주기마다 Live run이 기록되고, 리포트/알림이 운영 환경에서 확인 가능.

- G3 Evaluation Store & 회귀 자동화
  - EvaluationRun/override/정책 버전 불변 스토어 스키마/보존 정책 명문화, 삽입/조회 API 정리.
  - “나쁜 전략” 회귀 세트 큐레이션 → `scripts/policy_diff.py` 크론/CI 옵션화 → 임계 초과 시 경고/실패 플래그 설정.
  - 회귀 결과/히스토리 리포트(주간) 생성 경로 정의.
  - DoD: 스토어에 정책 버전별 기록이 남고, 회귀 배치가 임계 초과 시 실패 신호를 내며 리포트가 생성.

- G4 Portfolio/Stress 입력 소스 강화
  - gateway/리스크 엔진 프로듀서가 realized_returns_ref·stress ref를 risk hub에 push하도록 연결, 해시/actor/ACL 검증을 공통 모듈로 강제.
  - risk hub 스냅샷 계약(TTL 10s, sha256 hash, actor 헤더, offload 기준, 가중치 합≈1) 프로듀서·컨슈머 모두에 린터/테스트 추가.
  - DoD: 계약 위반 시 프로듀서 단계에서 거부/로깅되고, hub 컨슈머에서도 동일 기준으로 차단·알림.

- G5 SDK 얇게 만들기 & WS SSOT 전환
  - ValidationPipeline을 metrics-only 경로로 축소, 룰 실행·오케스트레이션을 WS 단일 진입으로 단계 전환(플래그/롤백 경로 포함).
  - WS 기반 통합 테스트(룰 실행·오류 처리·오프로드) 추가, SDK 호출부에는 디프리케이션 가이드 삽입.
  - DoD: 신규 경로가 기본값, SDK 경로는 metrics-only로 남고, 전환 실패 시 롤백 플래그로 복구 가능.

- G6 거버넌스/운영 가시성
  - 독립 검증(Repo/권한 분리) 경로와 override 재검토 큐 운영 모델 정의, 승인 SLA 명시.
  - SR 11-7 인바리언트, risk hub freshness/누락, extended validation 성공률·dedupe hit 메트릭 대시보드와 Alertmanager 룰 보강.
  - DoD: 승인/재검토 흐름이 런북에 반영되고, 메트릭/알람이 운영 환경에서 확인 가능.

## 공통 일정·추적 프레임
- 순서: G1 → G2 → G3/G4 병행 → G5 → G6(지속)으로 추진, 각 단계 종료 시 런북/알람/테스트 업데이트.
- 증빙: 리허설 로그, 대시보드 스냅샷, 알람 트리거 캡처, 회귀 리포트 샘플을 문서에 첨부.
- 검증: 코드 변경 시 CI 전체(uv mypy, mkdocs, docs 링크, 사이클, pytest -n auto, e2e world_smoke) 실행을 기본으로 하고, 큐/워커는 재시도·중복·TTL 초과 시나리오 수동 리허설 포함.

## 이번 사이클(2주) 실행 항목
- Week 1 — G1·G2 토대
  - ControlBus 템플릿 초안: 토픽/컨슈머 그룹/백오프·재시도/DLQ/헬스 메트릭 정의를 문서+코드에 반영, gateway·ExtendedValidation 워커에 적용 PR 착수.
  - Risk snapshot dedupe·알람: dedupe 키(해시+actor+stage) 공용 헬퍼 추가, 재시도/Alertmanager 룰 PR, 재처리/중복 리허설 로그 확보.
  - Live 스케줄러 골격: 30/60/90일 스케줄러 잡 생성, Live EvaluationRun 워커 엔드포인트 연결, decay 지표 계산 파이프라인 스텁 배치.
  - 증빙/검증: 큐 리허설 캡처, 스케줄러 dry-run 결과, mkdocs 링크·CI 기본 세트 실행 로그.

- Week 2 — G2 운영화 + G3/G4 착수
  - Live 리포트 템플릿/노출: 대시보드/API 초안과 샘플 출력 확정, 스케줄 지연/실패 알람 튜닝.
  - Evaluation Store 정책: 불변 스토어 스키마·보존 정책 결정, 삽입/조회 API 초안 문서화, “나쁜 전략” 회귀 세트 목록 작성.
  - Realized/Stress 프로듀서 연결: gateway/리스크 엔진에서 realized_returns_ref·stress ref push 경로와 해시/ACL 검증 헬퍼 추가 PR.
  - 증빙/검증: 회귀 세트 목록·스토어 스키마 리뷰 기록, 프로듀서 계약 위반 테스트 로그, CI 기본 세트 재실행.

## 실행 체크리스트 (담당/마감/증빙)
- G1 ControlBus 표준화
  - [ ] 토픽·그룹·백오프·DLQ 템플릿 PR (담당/마감/PR 링크)
  - [ ] dedupe 키 헬퍼 + 재시도·알람 규칙 PR (담당/마감/PR 링크)
  - [ ] 재처리/중복 리허설 로그·메트릭 캡처 첨부
- G2 Live 모니터링
  - [ ] 스케줄러 잡 배포 + dry-run 로그
  - [ ] Live EvaluationRun 워커/decay 계산 파이프라인 연결 PR
  - [ ] 리포트 템플릿·노출 경로 샘플 출력, 지연/실패 알람 캡처
- G3 Evaluation Store·회귀
  - [ ] 불변 스토어 스키마/보존 정책 확정 문서
  - [ ] 삽입/조회 API 초안 PR
  - [ ] “나쁜 전략” 회귀 세트 목록 + `scripts/policy_diff.py` 크론/CI 옵션 PR + 임계 초과 실패 플래그 검증 로그
- G4 Portfolio/Stress 입력
  - [ ] realized_returns_ref·stress ref 프로듀서 연결 PR
  - [ ] 해시/actor/ACL 검증 공용 모듈 + 린터/테스트 PR
  - [ ] 계약 위반 차단 로그·알람 캡처
- G5 SDK→WS 전환
  - [ ] ValidationPipeline metrics-only 축소 PR + 플래그/롤백 경로 문서
  - [ ] WS 통합 테스트(룰 실행·오류·오프로드) 추가 PR
  - [ ] SDK 디프리케이션 가이드 배포
- G6 거버넌스/가시성
  - [ ] override 재검토 큐·승인 SLA 문서
  - [ ] SR 11-7/메트릭 대시보드·Alertmanager 룰 PR
  - [ ] 런북 업데이트 및 대시보드/알람 스냅샷 첨부

## 최근 진행 업데이트
- ControlBus 경로 dedupe/TTL 계측: `risk_hub_snapshot_dedupe_total{world_id,stage}`·`risk_hub_snapshot_expired_total{world_id,stage}` 추가, 소비자에서 stage-aware 집계.
- Stage 헤더 전파: gateway 리밸런스→RiskHubClient `X-Stage` 전달, activation 스냅샷도 `stage=live` 부여, WS 라우터가 provenance.stage 기록.
- 런북/알림: ko/en Risk Signal Hub 런북에 헤더/TTL/dedupe 대응 추가, Alertmanager 룰에 dedupe/expired 스파이크 감지 룰 포함.
- 회귀 자동화(G3): `scripts/policy_diff_batch.py`가 stage 지정(`--stage`)과 runs 디렉터리 glob(`--runs-dir/--runs-pattern`)를 지원하여 “나쁜 전략” 세트+최신 runs를 묶어 크론/CI에서 임팩트 비율 임계(`--fail-impact-ratio`)로 실패 플래그를 낼 수 있음.

## G3 실행 가이드 (회귀/스토어)
- 크론/CI 스니펫: `uv run python scripts/policy_diff_batch.py --old baseline.yml --new candidate.yml --runs-dir artifacts/bad_strategies_runs --runs-pattern '*.json' --stage backtest --output policy_diff_report.json --fail-impact-ratio 0.05`
- 아티팩트: `policy_diff_report.json` 업로드, 임팩트 비율 초과 시 워크플로 실패 처리.
- 스토어/보존: EvaluationRun/override 불변 저장, 정책 버전별 히스토리 유지(최소 90일) → API/문서로 스키마 고정 필요(추후 PR).

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
