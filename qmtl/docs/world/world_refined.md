아래는 **현재 리서치 목적과 결과(설계 초안)**을 비판적으로 검토하고, 전면 개선 방향과 구체 보완안을 정리한 내용입니다. 실행 관점에서 즉시 반영 가능한 설계 수정안, 정책 DSL, 전환 알고리즘, 운영/관측 체계, 작업 목록까지 포함했습니다.

⸻

1) 리서치 목적의 적합성 & 간극

목적 요약
	•	월드(World)를 전략 상위 추상화로 두고, 현재 데이터 타임스탬프에 따라 제출된 전략을 백테스트→드라이런(모의 실현손익 추적 포함)→라이브로 정책 기반 자동 전환.
	•	전환/설정은 QMTL CLI/API(Gateway 연계)에서 외부 제어.
	•	임계값·Top‑K·상관·히스테리시스 등을 AND/OR로 조합 가능한 평가정책.

무엇이 잘 맞았는가
	•	QMTL이 PaperTrading↔Brokerage 전환, Runner, 성능 측정 노드(Sharpe, MDD 등) 및 메트릭 수집(예: Prometheus) 등을 이미 갖추고 있어 “검증→승격” 파이프라인이 자연스레 통합 가능합니다. 설계 초안에서도 Runner 모드 전환과 성능 수집/선정/Top‑K가 일관된 흐름으로 제시되어 있습니다.  ￼  ￼
	•	월드 경계에서 정책·리소스·관측을 묶고, 월드별 정책/Top‑K/히스테리시스·브로커리지·모드 전환을 관리하도록 한 방향성은 적절합니다. 구성 스키마(YAML)와 예시 CLI도 유용합니다.  ￼  ￼

핵심 간극(비판점)
	1.	시간·데이터 정합성 정의 부족
	•	“현재 데이터 타임스탬프에 따라 백테스트 vs 드라이런 시작”의 판별 규칙과 데이터 랙 허용치(예: exchange D+1 정산) 정의가 없다. 이 구간이 불명확하면 룩어헤드/서바이벌 바이어스가 스며들 수 있다.
	2.	표본 충분성/통계적 유의성 결여
	•	임계값/Top‑K 중심은 “평균적 우월성”은 보이지만, 표본 수(T, Nfills), 신뢰구간, 다중가설 보정(탐색 편향), 워크‑포워드/퍼지드 CV 등 과적합 방지 요소가 빠져 있다.
	3.	전환 원자성·안전성 시멘틱 미비
	•	드라이런→라이브 전환 시 이중 주문 방지, 세션 드레인, 청산/이월 규칙, 일시 동결과 롤백 등 금융 시스템의 필수 안전장치와 Idempotency 요건이 설계로 못 박혀야 한다.
	4.	포트폴리오·리스크 총량 관리 부족
	•	상관 제약만으로는 불충분. 월드 레벨 리스크 버짓(예: VAR, gross/net, sector/asset cap, side별 한도), 마진/레버리지 제약, 드로우다운 컷·서킷브레이커가 필요.
	5.	멀티‑월드·공유 노드 운영 위험
	•	World‑SILO/SHARED 혼합은 비용에 유리하지만, 경계/권한/자원 격리와 가지치기(Mark‑&‑Sweep) 시 안전 드레인 규칙이 강제되지 않으면 운영 리스크가 있다. 초안에 방향성은 있으나 보호장치가 부족하다.  ￼
	6.	운영성(관측·감사·권한)
	•	정책/상태 변경에 대한 감사로그, 버전 롤백, SLO/알림 룰 표준화가 필요. 초안에 모니터링 연결 아이디어는 있으나, 필수 SLO와 알림 레벨이 정의돼야 한다.  ￼

⸻

2) 개선된 전체 설계 (핵심 제안)

A. 시간·데이터 시맨틱: “데이터 통화성(Data Currency) 게이트”
	•	world.data_currency: max_lag(예: 5m/1d), min_history(예: 60D), bar_alignment(세션 캘린더), warmup_periods(노드별 최댓값).
	•	상태 결정 알고리즘
	1.	t_data_end(해당 월드 데이터 레이크의 최신 시각), t_now, max_lag 비교.
	2.	t_now - t_data_end <= max_lag이면 드라이런 시작, 아니면 백테스트 모드로 Catch‑Up Sim(데이터가 실시간에 수렴할 때까지) → 이후 자동 드라이런 전환.
	3.	각 지표는 metric별 최소 표본 조건(예: Sharpe: N≥30일, 거래횟수≥K, 유효 바 수≥M) 충족 전에는 ‘참고’ 단계로만 사용.
	•	이 로직은 초안의 Runner/월드 스케줄 구조와 자연스럽게 결합된다(드라이런/라이브 전환은 Runner 재시작 없이 WS 활성 게이트만 조정한다).

B. 평가 정책 DSL: 게이트(절대/상대) + 점수 + 제약의 3층
	•	게이트(Gate): 임계값·샘플충분성(표본 수, 유효 일수, 체결수), 안정성(변동성, 자본곡선 slope t‑stat) 조건 AND/OR 합성.
	•	점수(Score): 사용자 정의 가중합/함수(예: 중기 Sharpe + 0.1×장기 승률 − 0.2×Ulcer). 상위 정렬로 Top‑K 선정.
	•	제약(Constraints): 상관/공분산 기반 군집 제한, 섹터·심볼·사이드(Long/Short)·브로커 한도.
	•	히스테리시스/쿨다운: 승격/강등의 On/Off 이원 임계, 최소 체류 시간(min dwell), 평가주기 K회 연속 기준.
	•	월드 YAML 예시(사이드 파라미터 분리 포함):

selection:
  gates:
    and:
      - sharpe_mid >= 0.60
      - trades_60d >= 40
      - max_dd_120d <= 0.25
      - sample_days >= 30
  score: "sharpe_mid + 0.1*winrate_long - 0.2*ulcer_mid"
  topk:
    total: 8
    by_side: { long: 5, short: 3 }     # 롱/숏 분리
  correlation:
    max_pairwise: 0.85
  hysteresis:
    promote_after: { windows: 2 }       # 2회 연속 통과
    demote_after:  { windows: 2 }       # 2회 연속 미달
    min_dwell: "10D"

(월드 정책·Top‑K·히스테리시스·상관 제약 구조는 기존 제안과 호환)  ￼  ￼

C. 드라이런→라이브 전환의 원자성(Atomic Cutover)
	•	2‑Phase 전환 프로토콜
	1.	Freeze: 전략 신호 게이트 노드 OFF(주문 차단), 미집행 오더 취소, 체결 스트림 드레인.
	2.	Switch: WS 활성 게이트를 ON으로 전환하고 `Runner.run(world_id=..., gateway_url=...)` 상태에서 실계좌 Brokerage 바인딩·계좌/권한 검증·idempotent run_id 발급을 수행한다.
	3.	Unfreeze: 게이트 ON, 첫 N틱은 모니터링만(선택), 이후 정상 주문.
	•	포지션 정책(월드별): position_transition = { on_promote: "none|mirror|close_and_reopen", on_demote: "market|twap|none" }
	•	기본값은 미이월(시장가 진입/청산 없음). 접근성은 있으되 보수적 기본값으로 사고 위험을 낮춤.
	•	초안이 제시한 PaperTrading↔Brokerage 전환을 원자화·안전장치와 함께 고정시킵니다.  ￼

D. 월드 레벨 리스크 엔진(필수)
	•	총량 한도: Gross, Net, Side별(롱/숏), 심볼·섹터·거래소, 레버리지/마진 한도.
	•	실시간 컷: World‑Wide Drawdown(예: 5% Intraday), 일중 손실 한도, 체결 거부율/연결 오류율 기반 서킷 브레이커.
	•	선정과 병렬: Top‑K로 ‘무엇을’ 고르고, 리스크 엔진으로 ‘얼마나’ 할지를 결정. (선정=구성, 리스크=용량 배분/제약)

E. 멀티‑월드·공유 노드의 안전 운영
	•	World‑SILO 기본, SHARED 선택: NodeID는 글로벌(GSG)이며 world_id를 포함하지 않는다. 공용 지표/원시 데이터는 share_scope=GLOBAL로 허용하고, 월드 격리는 Kafka topic_prefix/WVG(World View Graph)에서 수행한다(점진 도입).
	•	Mark‑&‑Sweep + 드레인: 월드별 활성 알파 집합을 기준으로 역방향 마킹 후, **드레인 시간(최대 period×interval)**을 보장하고 비표시 노드만 정리. 버전드 DAG + 롤백 포인트 필수.  ￼
	•	초안의 가지치기/파티셔닝 원칙을 안전장치 포함으로 강화.  ￼

F. 운영·관측·감사
	•	SLO: (i) 승격/강등 지연 ≤ 1 평가주기, (ii) 전환 실패율 < 0.5%, (iii) 메트릭 계산 지연 < 1m.
	•	감사 로그: who/when/what(policy_id, diff) + 재현성 스냅샷(정책/데이터 버전, 지표 스냅샷, 결정 트리) 저장.
	•	알림 표준화: 승격/강등/서킷/실패/지연 레벨. 기존 메트릭·알림 연계 아이디어를 자동 액션과 묶음.  ￼

⸻

3) 정책/아키텍처 보강: 적용 청사진

(1) WorldService(신규 서비스, 경계 명확화)
	•	책임: 정책 파싱/검증 → 평가주기 실행 → 후보 선별(게이트→스코어→제약→Top‑K) → 전환 트랜잭션 발행.
	•	상태기계(FSM): submitted → backtest → dry-run(evaluating) → live → inactive(←→dry-run)
	•	Gateway 연결: Gateway는 실행/상태 저장에 집중, WorldService는 정책·결정에 집중(약결합).
	•	기존 Runner/메트릭 수집을 그대로 활용(설계 초안과 호환).  ￼  ￼

(2) API/CLI (외부 제어)
	•	CLI
	•	qmtl world apply -f world.yml (정책/리소스 버전 적용)
	•	qmtl world eval <world_id> --now (즉시 평가 트리거)
	•	qmtl world activation set <world_id> --strategy <sid> --side long|short --active true|false (강제 개입)
	•	API
	•	POST /worlds/{id}/policy(버전드), POST /worlds/{id}/state(Active/EvalOnly/Paused)
	•	POST /worlds/{id}/evaluate, POST /strategies/{sid}/promote|demote
	•	권한: world‑scope RBAC(Owner/Operator). 초안의 CLI/구성과 일치하되 경계·권한을 더 명확히.  ￼

(3) 평가 엔진: 결정의 재현성과 안전성
	•	결정 함수 decide(world_snapshot) -> plan: 입력(정책 버전·지표 스냅샷·Top‑K 계산 기록)을 불변 스냅샷으로 받아 순수 함수처럼 동작 → 결과(plan)를 원자 적용.
	•	쿨다운/히스테리시스: 정책에 명시된 promote_after/demote_after/min_dwell.
	•	샘플충분성: metric별 min_trades, min_days, min_bars를 gate에 반드시 포함. (예: Sharpe 통계적 신뢰 낮을 땐 ‘참고’만)

⸻

4) 실패 모드와 방어선 (현장 체크리스트)
	•	토글 플리커: 히스테리시스+쿨다운+min_dwell로 차단(정책 기본값을 보수적으로).  ￼
	•	이중 주문/유령 포지션: 게이트 노드 + 2‑Phase 전환 + 미집행 오더 취소 + idempotent run_id.
	•	과적합: walk‑forward, purged CV, deflated Sharpe(추가 분석 파이프).
	•	데이터 공백/지연: data_currency 게이트(정책상 max_lag 위반 시 자동 Eval‑Only).
	•	공유 노드 청소 중 오차: Mark‑&‑Sweep에서 드레인 보장과 버전 롤백.  ￼

⸻

5) 적용을 위한 세부 작업 목록(개선판)

A. 도메인/스토어
	1.	World, WorldPolicy(vN), StrategyInstance 스키마 + 상태FSM 컬럼/인덱스.  ￼
	2.	감사/결정 로그 테이블(정책 diff, 입력 지표 스냅샷, Top‑K 결과, 전환 plan, 실행 결과).

B. 정책/평가
3. Policy DSL(Gate/Score/Constraint/Hysteresis) 파서 + 검증기.
4. 샘플충분성 게이트(metric별 min sample), data_currency 게이트(max_lag/min_history).
5. 평가 엔진(순수 결정 함수 + 스냅샷 로딩) 및 스케줄러(APScheduler/cron).

C. 실행/전환
6. 게이트 노드(Order 앞단 AND 스위치) 및 글로벌 활성 테이블(런타임 조회).  ￼
7. 2‑Phase 전환기: Freeze/Drain→Switch→Unfreeze, idempotent run_id, 실패 롤백.
8. 포지션 정책(on_promote/on_demote) 적용기(기본 미이월).

D. 멀티‑월드/자원
9. World‑SILO 기본/SHARED 선택: NodeID 해시 스킴, Kafka 네임스페이스, 파티션 뷰.  ￼
10. Mark‑&‑Sweep with Drain + 버전드 DAG/롤백 체크포인트.  ￼

E. 관측/운영
11. SLO/알림 룰 표준화(승격/강등/실패/지연/서킷). 기존 메트릭과 연계(알림→액션).  ￼
12. CLI/API 확장(버전 적용, 즉시 평가, 강제 모드 전환), world‑scope RBAC.  ￼

⸻

6) 사용자가 중시한 “파라미터 분리” 반영
	•	사이드별 분리: topk.by_side, gates.side.long/short, 자금·리스크 버짓도 side별로 분리. (예: gross_budget: { long: 60%, short: 40% })
	•	전략 파라미터 분리: 동일 전략 코드라도 StrategyInstance(params)를 월드/사이드 별 인스턴스로 관리.  ￼

⸻

7) 기대 효과(시나리오: +/0/−)
	•	긍정(+): 월드 경계에서 정책/리소스/관측을 분리, 자동 전환 안전성↑, 비용은 공유 노드로 절감. 승격/강등의 판정 재현성과 감사 추적성 확보.  ￼
	•	중립(0): SHARED 도입으로 구성 복잡도↑. SILO 기본 → SHARED 점진 도입 전략이면 초기 리스크 관리 가능.  ￼
	•	부정(−): 드레인/히스테리시스/리스크 컷이 없으면 토글·자원 난립·예상치 못한 주문 발동 위험. (정책 기본값 보수적 설정 권고)  ￼

⸻

8) 한눈에 보는 “개선된 상태 결정” 의사 코드

def decide_initial_phase(world, now, data_end):
    if (now - data_end) <= world.data_currency.max_lag:
        Runner.run(world_id=world.id, gateway_url=world.gateway_url)
    else:
        Runner.offline(world.strategy_cls)

def gate_metrics(metrics, policy):
    if metrics.sample_days < policy.min_sample_days: return "insufficient"
    if metrics.trades_60d < policy.min_trades: return "insufficient"
    # 임계값/AND-OR 조합
    return "pass" if eval_expr(policy.gates, metrics) else "fail"

def hysteresis(prev_state, checks, policy):
    dwell_ok = time_in_state(prev_state) >= policy.hysteresis.min_dwell
    if checks.consecutive_pass >= policy.hysteresis.promote_after and dwell_ok:
        return "PROMOTE"
    if checks.consecutive_fail >= policy.hysteresis.demote_after and dwell_ok:
        return "DEMOTE"
    return "HOLD"


⸻

9) 본 설계가 기존 결과와 합치/강화되는 지점
	•	Runner.run 기반 전환·PaperTrading↔Brokerage 전환은 그대로 활용하되, 게이트 노드+2‑Phase 전환으로 금융 시스템에 필요한 원자성·안전장치를 부여.  ￼
	•	월드 정책/Top‑K/히스테리시스·가지치기(Mark‑&‑Sweep) 구상은 유지하되, 데이터 통화성/표본충분성/리스크 총량을 정식 게이트로 승격.  ￼  ￼
	•	CLI/API는 Gateway를 기본 채널로 하되, WorldService를 분리해 구조적 명확성 확보(정책 결정은 WorldService, 실행/상태는 Gateway).  ￼

⸻

마치며

제안된 개선안은, 이미 문서에서 강점으로 식별된 월드 경계·Runner.run 기반 전환·성과 측정 인프라(Prometheus/성능노드)와 전역 DAG 재사용을 유지하면서, 시간/표본/전환/리스크/운영 5축의 빈틈을 메워 실전 안전성과 재현성을 크게 끌어올립니다. 필요하시면 위 정책 DSL 스키마와 2‑Phase 전환기를 바탕으로 world.yml 템플릿·API 명세·통합 테스트 시나리오까지 한 번에 정리해 드리겠습니다.
