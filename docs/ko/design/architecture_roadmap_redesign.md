---
title: "Core Loop 아키텍처 로드맵 재설계 — 설계 합의 문서"
tags: [architecture, roadmap, design-decision]
author: "QMTL Team"
last_modified: 2025-12-04
status: approved
---

!!! success "설계 합의 완료 (2025-12-04)"
    이 문서는 초기 제안과 4개의 검토 의견(의견 1~4)을 거쳐 **설계 합의가 완료**된 상태입니다.  
    종합의견에서 도출된 8가지 방향은 `core_loop_roadmap.md`에 반영되었습니다.  
    이 문서는 설계 결정의 근거와 논의 과정을 보존하는 **아카이브 문서**로 유지됩니다.

---

# Core Loop 아키텍처 로드맵 재설계

좋은 문제 의식입니다. 지금 상태를 정리하면:
	•	여러 설계 문서(architecture / gateway / worldservice / seamless)가 As‑Is와 To‑Be가 섞인 상태로 존재하고,
	•	core_loop_roadmap.md는 To‑Be를 잘 모아 놓았지만,
	•	실제 구현은 “기존 모듈 재활용 + 소극적 리팩터링”으로 흘러갈 위험이 있고,
	•	당신이 원하는 것은 Core Loop 방향성에 맞춰 과감하게 잘라낼 것은 자르고, 재설계할 것은 재설계하는 로드맵입니다.

아래는 그 관점에서 정리한 “종합 로드맵 프레임”과, 어디를 과감하게 갈아엎어야 하는지 그리고 “소극적인 대응”을 구조적으로 막는 방법입니다.

⸻

1. 우선 문제/위험 요약

현재 구조에서 방향성을 잃기 쉬운 지점들을 먼저 짚겠습니다.
	1.	As‑Is / To‑Be 혼재
	•	문서 곳곳에서 “As‑Is / To‑Be”가 잘 적혀 있지만, 코드/구현 상에서는
	•	Runner.submit,
	•	ValidationPipeline,
	•	WorldService/Gateway,
	•	Seamless
사이 역할 구분이 아직 완전히 정리되지 않았습니다.
	•	이 상태에서 “기존 모듈 최대 재활용 + 작은 변경” 위주로 작업이 진행되면,
To‑Be는 설계 문서에만 존재하는 이상향이 되고 시스템은 계속 과거 아키텍처의 관성을 따르게 됩니다.
	2.	중복 책임과 이중 진실(SSOT 붕괴 위험)
	•	ValidationPipeline vs WorldService 정책 엔진
	•	Runner/SDK의 execution_domain 힌트 vs WorldService effective_mode
	•	전략 코드의 history_provider 지정 vs world/preset 기반 Seamless 자동 와이어링
	•	이런 “이중 진실”이 유지되는 동안은, 아무리 좋은 To‑Be를 써 두어도 실제 구현이 그쪽으로 수렴하기 어렵습니다.
	3.	‘조금씩 고치는 식’의 구조적 유혹
	•	Gateway/DM/WS/Seamless가 이미 복잡하기 때문에, 각 모듈 담당자가 자기 모듈 안에서만 해결하려고 하면:
	•	레거시 엔드포인트와 새 엔드포인트가 병존
	•	ExecutionDomain/ComputeContext 규약이 곳곳에서 미묘하게 달라짐
	•	“Core Loop E2E 경험”은 계속 깨진 채, 내부 구현만 복잡해지는 상황이 나옵니다.

이걸 깨려면 “트랙별 개선”만으로는 부족하고, Core Loop 전체에 걸친 수직 슬라이스(End‑to‑End Vertical Slice) 기준으로 로드맵을 다시 묶어야 합니다.

⸻

2. 상위 원칙 정리 (North Star & 금지 원칙)

이미 문서에 등장하는 가치들을, 로드맵 관점에서 실제 규칙으로 재정의하면 다음 네 가지입니다.
	1.	“Runner.submit만 알면 된다”를 진짜로 만들 것
	•	최종 상태(To‑Be)에서:
	•	전략 작성자는 신호 + 월드 + (선택적) 데이터 preset만 지정
	•	Runner.submit(..., world=..., mode=...) 한 번으로
warm‑up + 백테스트 + WorldService 평가 + 활성/배포 후보 생성까지 잇달아 실행
	•	이걸 만족시키지 않는 기능은 “코어 루프 바깥의 부가 기능”으로 취급해야 합니다.
	2.	SSOT 고정: World/Graph/Data Plane
	•	정책/평가/게이팅/자본 배분 → WorldService가 유일한 진실
	•	그래프/큐/NodeID/ComputeKey → DAG Manager가 유일한 진실
	•	데이터 품질/백필/SLA → Seamless/Data Plane이 유일한 진실
	•	Runner/SDK, Gateway는 Thin Boundary Layer만 허용 (로직 중복 금지)
	3.	Default-Safe, 모호하면 무조건 backtest/compute‑only
	•	ExecutionDomain, as_of, dataset_fingerprint, allow_live 등에서
조금이라도 모호하면:
	•	라이브는 절대 열지 않고
	•	backtest + 주문 게이트 OFF 상태로 강등 (compute‑only)
	4.	단순성 > 하위 호환성
	•	“신 방식”이 준비되면:
	•	레거시 엔드포인트/플래그/모드는 명시적인 deprecation + 제거 계획을 함께 가져가야 합니다.
	•	“구/신 두 가지 방식을 문서에 계속 같이 두는 것” 자체를 명시적으로 금지하는 것이 중요합니다.

이 네 가지를 로드맵의 최상위 constraint로 두고, 그 아래에 작업 트랙들을 배치해야 방향성이 유지됩니다.

⸻

3. 트랙 중심(T1–T6)에서 수직 슬라이스 중심으로

core_loop_roadmap.md의 T1–T6 트랙은 좋은 분류지만, “모듈별 리팩터링” 관점이 강해서 방금 말한 문제(국지적 최적화)로 흐를 위험이 있습니다.
그래서 상단에 3개의 End‑to‑End 프로그램을 두고, T1–T6는 그 아래에 매핑되는 구조를 제안합니다.

3.1 프로그램 P‑A: Core Loop Paved Road v1

목표:
“신규 전략 작성자가 QMTL을 처음 쓸 때 **딱 한 가지 길(포장된 도로)**만 보이고, 그 길은 Core Loop 방향성을 정확히 구현한다.”

스코프 (End‑to‑End):
	1.	Strategy 코드
	2.	Runner/SDK (Runner.submit, CLI)
	3.	Gateway /strategies, /queues/by_tag
	4.	WorldService /decide, /evaluate, /activation
	5.	Seamless 기본 preset을 통한 데이터 공급
	6.	SubmitResult / CLI 출력 / 관측

여기서 P0로 반드시 끝내야 할 것:
	•	P‑A‑1: SubmitResult ↔ WorldService Envelopes 1:1 정렬
	•	Runner.submit의 결과 타입을 DecisionEnvelope + ActivationEnvelope (+ ValidationPipeline 메트릭) 구조로 고정
	•	“최종적으로 이 전략이 월드에서 어떻게 취급되었는지”를 한 눈에 볼 수 있어야 함
	•	P‑A‑2: ExecutionDomain 결정 권한을 WorldService로 100% 이동
	•	Runner/SDK와 Gateway에서 meta.execution_domain은 오직 힌트로만 취급
	•	실제 실행 도메인은 항상 DecisionEnvelope.effective_mode에서 유도
	•	코드 레벨에서 “WS 없이 Runner가 도메인 강제”하는 경로는 제거
	•	P‑A‑3: world/preset 기반 Seamless auto‑wiring의 최소 버전
	•	world/world.md에 “data preset → Seamless provider 구성”을 명시하고,
	•	Runner/CLI가 world만으로 기본 Seamless provider를 붙여 줄 수 있는 최소 기능을 만든 뒤,
	•	전략 코드 내 history_provider 직접 인스턴스화는 “고급/override”로 위치를 낮춘다.
	•	P‑A‑4: “Runner.submit 한 번으로 끝나는 예제”를 public 기준으로 삼기
	•	docs/guides, 튜토리얼, 템플릿이 모두 이 Paved Road를 기준으로 다시 작성
	•	기존 “순수 로컬 모드” 예제는 부록/appendix로 이동

이 Program P‑A가 끝나면, QMTL은 “As‑Is/To‑Be가 섞인 플랫폼”이 아니라
“명확한 하나의 ‘신 방식’이 존재하고, 나머지는 점진적으로 제거되는 플랫폼”이 됩니다.

3.2 프로그램 P‑B: Promotion & Live Safety

목표:
backtest → dryrun → live 승급 경로와 2‑Phase Apply, Feature Artifact Plane, dataset_fingerprint를 하나의 승급 프로토콜로 묶고, 이 경로 이외의 라이브 이동을 막는다.

핵심 구성 요소:
	•	WorldService의 effective_mode → ExecutionDomain 매핑
	•	2‑Phase Apply: Freeze/Drain → Switch → Unfreeze
	•	Feature Artifact Plane (불변 factor artifacts + dataset_fingerprint)
	•	EdgeOverride (backtest→live cross‑domain edge 정책)

여기서 P0로 반드시 해야 할 것:
	•	P‑B‑1: 2‑Phase Apply를 “옵션”이 아니라 “유일한 live promotion 경로”로
	•	WS/Docs에서 “라이브 승급은 무조건 2‑Phase Apply로만 가능하다”는 규범화
	•	Gateway/SDK가 다른 방식(예: 단순 ExecutionDomain 변경)으로 라이브로 들어가는 것을 금지
	•	P‑B‑2: Feature Artifact Plane 강제
	•	라이브/섀도우 도메인에서 ComputeKey 기반 캐시 공유 금지를 실제 코드 수준에서 enforce
	•	cross‑domain cache hit 시 실패로 간주하고 메트릭/로그 남기기
	•	P‑B‑3: dataset_fingerprint 없이는 live로 못 가게
	•	WS 정책에서, 프로모션 정책에 dataset_fingerprint가 없으면 apply 거부
	•	Gateway/Runner도 해당 invariant를 인지하고 에러 메시지에서 이유를 명확히 표시

3.3 프로그램 P‑C: Data Autopilot & Observability

목표:
데이터 플레인(Seamless)이 Core Loop에서 약속하는 품질/SLA/백필을 실제로 uphold하고, Core Loop 각 단계의 상태를 하나의 대시보드에서 볼 수 있게 하는 것.

핵심 구성 요소:
	•	Seamless Data Provider v2 (ConformancePipeline, SLA, 분산 백필)
	•	world/preset ↔ 데이터 preset 매핑
	•	Core Loop용 골든 시그널
	•	“submit→warm‑up 지연”, “백테스트 coverage”, “WS 평가 지연”, “활성 반영 지연”

이 Program은 이미 Seamless 쪽 As‑Is/To‑Be가 꽤 진전되어 있어서, Core Loop에 맞춰 표면만 정리하면 되는 부분이 많습니다.

⸻

4. 어디를 “과감하게” 재설계해야 하는지 (핫스팟 5곳)

이제 “소극적인 대처로는 안 되는”, 실질적으로 구조를 바꿔야 하는 지점을 딱 짚어보겠습니다. 각 항목마다 소극적 대응 vs 과감한 대응을 대비시킵니다.

4.1 SDK/Runner: ValidationPipeline vs WorldService
	•	현재 상태
	•	ValidationPipeline도 pass/fail, weight 같은 개념을 갖고 있고,
	•	WorldService도 active/weight/contribution을 갖고 있음.
	•	문서는 “WS가 SSOT”라고 하지만, 코드/사용자 경험으로 보면 이중 진실.
	•	소극적 대응
	•	“WS 결과를 나중에 참고” 정도로만 Runner에 보여 주고, ValidationPipeline을 계속 거의 그대로 유지.
	•	과감한 대응 (추천)
	1.	ValidationPipeline에서 “정책/게이팅” 개념을 제거하고,
	•	지표 계산 + 로컬 sanity check 용도로 축소
	2.	“이 전략이 월드에서 활성인지, weight가 얼마인지, tradable인지”는 오직 WS 결과만 의미하도록 명시
	3.	SubmitResult는 다음 구조로 고정:
	•	ws_decision: DecisionEnvelope
	•	ws_activation_summary: { active, weight, mode }
	•	local_metrics: ValidationPipeline 결과 (참고용)
	4.	문서에서 “ValidationPipeline의 PASS/FAIL은 정책이 아니다”라고 못을 박고, WS 정책 YAML만이 gate를 의미하게 만들 것.

이건 코드 삭제 + 책임 축소가 필요하기 때문에, 의식적으로 “ValidationPipeline slimming”이라는 이름의 이슈/에픽으로 잡는 것이 좋습니다.

4.2 ExecutionDomain: Runner/SDK 힌트 제거
	•	현재 상태
	•	Runner.submit에서 mode/execution_domain를 넣을 수 있고,
	•	Gateway/WS에서 effective_mode & execution_domain을 다시 결정함.
	•	도메인 결정 로직이 세 군데에 흩어져 있음.
	•	소극적 대응
	•	“WS가 우선”이라고 문서에 쓰고, 코드 상에서는 힌트를 남겨 둔 채, conflict 시 warnings 정도만 찍음.
	•	과감한 대응 (추천)
	1.	Runner/SDK에서 mode 인자를 semantic히 다음 정도로만 한정:
	•	'backtest' / 'dryrun' / 'live' / 'shadow' → “사용자 기대” 수준
	2.	Gateway 진입 시:
	•	이 값은 로깅 + UX 메시지용 힌트로만 쓰고,
	•	실제 execution_domain은 항상 WS effective_mode에서 파생.
	3.	Runner/SDK 코드에서 “execution_domain을 직접 강제하는 코드 경로”를 제거.
예: “WS 없이도 live로 실행” 같은 모드는 테스트용 별도 helper로 분리.
	4.	이 변경을 “ExecutionDomain Centralization” 같은 제목의 ADR/설계 이슈로 공식화해서, 이후 누구도 Runner 쪽에 도메인 로직을 새로 추가하지 못하게 하는 것.

4.3 history_provider 직접 구성 vs Seamless preset
	•	현재 상태
	•	Strategy에서 StreamInput(... history_provider=...)를 직접 주입하는 패턴이 기본 예제로도 존재.
	•	Seamless v2는 이미 준비되어 있지만, Core Loop 상에서는 “선택적” 인상.
	•	소극적 대응
	•	“world로 Seamless를 붙이는 helper 추가” 정도에서 멈추고, 문서에 둘 다 설명해둔다.
	•	과감한 대응 (추천)
	1.	공식 가이드/템플릿에서 history_provider 직접 인스턴스화 예제를 제거.
	2.	대신:
	•	world 설정에 데이터 preset (ohlcv:binance:1m:crypto, 등)을 명시
	•	Runner가 world를 보고 Seamless provider를 자동 구성
	3.	Strategy 코드 설계 가이드에 다음 규칙 명시:
	•	“표준 사용자는 history_provider를 직접 건드리지 않는다”
	•	직접 건드리는 경우는 “실험/커스텀 데이터 파이프라인”이며, Core Loop의 품질 보증(SLA/SLA 정책) 밖이다.
	4.	구현 상으로도:
	•	Runner/SDK에 “history_provider가 없으면 world/preset으로 Seamless 붙이기”를 기본 케이스로 두고,
	•	직접 provider를 넣었을 때는 경고 메트릭을 찍어 “paved road에서 벗어났다”는 신호를 남기기.

4.4 TagQuery / NodeID 결정성
	•	현재 상태
	•	TagQueryNode의 NodeID는 “query spec 기반 canonicalization”이 문서에 있음.
	•	하지만 구현·테스트 수준에서 이 규약이 얼마나 강하게 enforce되는지는 별도.
	•	소극적 대응
	•	“노드 해시 규약을 문서화하고, 몇 개 테스트만 추가”.
	•	과감한 대응 (추천)
	1.	NodeID CRC 파이프라인을 필수로:
	•	SDK가 제공한 node_id vs Gateway가 재계산한 node_id가 다르면 무조건 400
	2.	TagQueryNode에 대해서:
	•	“동일한 query spec이면 NodeID가 무조건 동일”을 property test로 보장
	•	추가로, “동일 NodeID인데 upstream queue set이 시간에 따라 바뀌어도, 그것은 런타임 concern이고 canonical spec에는 영향을 못 준다”는 invariant를 테스트로 잡기.
	3.	“TagQuery 확장하며 NodeID 바꾸는 편의 기능”은 아예 금지하거나 실험적 플래그로 옮기기.

4.5 WorldService: 정책/승급/할당을 Core Loop와 맞물리게 재구성
	•	현재 상태
	•	WorldService는 상당히 정리되어 있고, /evaluate·/apply·/allocations까지 있다.
	•	다만 Runner/CLI 경험과 완전히 “한 화면/한 흐름”으로 연결되진 않았음.
	•	소극적 대응
	•	WorldService 쪽만 다듬고, Runner/CLI는 기존 스타일에 약간의 필드만 추가.
	•	과감한 대응 (추천)
	1.	Runner/CLI의 SubmitResult에 WS 평가/활성 요약을 1급 구성요소로 포함:
	•	평가 메트릭, 정책 버전, effective_mode, 활성 여부, weight, promotion 계획 등
	2.	CLI에서 qmtl world status류 명령이
“최근 제출된 전략과 world-level allocation”을 한 번에 보여주는 Core Loop 뷰가 되게 구성.
	3.	/allocations와 리밸런싱 API를 “전략 제출 → 평가 → (운영자가) 자본 배분 API 호출” 흐름으로 문서에서 연결.

⸻

5. 로드맵 문서(core_loop_roadmap.md)를 어떻게 손볼지

이미 T1–T6 트랙이 잘 정의되어 있으므로, 제가 제안하는 건:
	1.	문서 상단에 지금 말한 3개 프로그램(P‑A/B/C)을 추가하고,
	2.	각 프로그램이 T1–T6의 어떤 마일스톤을 “소비”하는지 매핑표를 넣는 것.

예시:
	•	P‑A (Core Loop Paved Road v1)
	•	T1‑M1, M2, M3 (SDK/SubmitResult, 실행모드 정규화, 템플릿)
	•	T2‑M1 (WS 평가/활성 단일화)
	•	T3‑M1 (world 기반 데이터 preset)
	•	T4‑M1, M2 (ComputeContext, NodeID/TagQuery 규약)
	•	T6‑M1 (Core Loop 계약 테스트)
	•	P‑B (Promotion & Live Safety)
	•	T2‑M2, M3 (ExecutionDomain/effective_mode, 2‑Phase Apply)
	•	T4‑M3 (큐 네임스페이스/ACL)
	•	T3‑M3 (Feature Artifact Plane와 dataset_fingerprint 적용)
	•	T5‑M1 (Determinism 체크리스트)
	•	P‑C (Data Autopilot & Observability)
	•	T3‑M1, M2 (Seamless preset, 스키마 거버넌스)
	•	T5‑M2 (Core Loop 골든 시그널 대시보드)
	•	T6‑M3 (As‑Is/To‑Be 문서 정리)

이렇게 하면, 각 PR/이슈는 반드시 “어느 프로그램의 어느 마일스톤을 전진시키는가?”를 명시하게 만들 수 있고, 국지적 최적화의 위험을 줄일 수 있습니다.

⸻

6. “소극적 대응”을 구조적으로 막는 운영 장치

마지막으로, 실제 개발 과정에서 방향성이 다시 흐려지는 걸 막기 위한 프로세스 레벨 가드레일을 제안합니다.
	1.	ADR + Program 태깅
	•	아키텍처 수준 변경/새 기능은 간단한 ADR(Architecture Decision Record)로 남기고,
	•	각 ADR에 “연결된 프로그램(P‑A/B/C)과 트랙/마일스톤”을 반드시 명시.
	•	“어느 프로그램에도 속하지 않는 변경”은 기본적으로 거부.
	2.	“신 방식이 하나라도 준비되면, 구 방식 deprecation 타이머 시작”
	•	예: world/preset 기반 Seamless가 P‑A‑3 수준으로 동작하기 시작하면:
	•	문서에서 history_provider 직접 구성은 “deprecated”로 표시,
	•	다음 릴리스/두 릴리스 내에 삭제 계획을 명시.
	3.	Core Loop 계약 테스트를 CI Gate로
	•	tests/e2e/core_loop 안에:
	•	“전략 작성→Runner.submit→WS 평가→Activation→(가짜)자본 배분” 시나리오를 자동 검증하는 테스트 세트 구축.
	•	CI에서 이 테스트가 깨지면 어떤 모듈 변경도 merge 불가.
	4.	관측 지표 기반의 Regression Watch
	•	Core Loop용 골든 시그널(제출 지연, WS 결정 지연, live promotion latency 등)에 대해 SLO를 걸고,
	•	리그레션이 발생하면 “로드맵 상 어느 프로그램을 역행했는지”를 회고 문서에 남기는 식으로 운용.

⸻

7. 다음 단계 제안

당장 실행 가능한 순서를 제안하면:
	1.	core_loop_roadmap.md 상단에 P‑A/B/C 프로그램 섹션 추가
	•	지금 정리한 수준의 텍스트를 프로그램 소개로 넣고,
	•	아래 기존 T1–T6 마일스톤을 각 프로그램에 매핑.
	2.	P‑A의 P0 범위를 더 구체화
	•	Runner.submit 반환 타입 개편 설계 스케치
	•	ExecutionDomain 중앙화 ADR 초안
	•	world/preset → Seamless auto‑wiring 최소 설계
	3.	ValidationPipeline 슬리밍 / WS SSOT화에 대한 별도 설계 문서
	•	“ValidationPipeline에서 무엇을 제거할 것인가?”와
	•	“WS 정책 엔진이 어떤 책임을 100% 가져갈 것인가?”를 명시.
	4.	Core Loop 계약 테스트 스켈레톤 작성
	•	아직 구현이 완벽하지 않아도, “이 테스트가 결국 통과해야 한다”는 스켈레톤을 만들어 두면,
	•	이후 작업들이 자연스럽게 그 테스트를 통과하도록 방향을 잡게 됩니다.

⸻

요약하면, 이미 문서에 있는 To‑Be는 상당히 잘 정리되어 있습니다.
지금 필요한 것은:
	•	그 To‑Be를 **3개의 수직 프로그램(P‑A/B/C)**로 묶고,
	•	각 프로그램이 반드시 Core Loop 경험을 전진시키도록,
	•	“ValidationPipeline vs WS”, “Runner.mode vs effective_mode”, “history_provider vs Seamless preset” 같은 핫스팟에서 과감하게 책임을 잘라내는 것입니다.

원하시면 다음 단계로, core_loop_roadmap.md의 실제 내용을 기반으로 프로그램 섹션을 어떻게 구체적으로 수정/추가할지, 문장 단위 초안까지 같이 잡아볼 수 있습니다.

⸻

의견1. 로드맵 개선 방향에 대한 메모

- P‑A/B/C 프로그램 단위로 로드맵을 재편하는 방향은 타당하고, Core Loop 경험을 기준으로 PR/이슈를 정렬하는 데 도움이 됩니다.
- 다만 “어느 프로그램에도 속하지 않는 변경은 거부” 규칙은 인프라·운영·관측 개선 같은 주변 작업까지 모두 끼워 넣게 만들 수 있으므로, 공통 인프라/플랫폼을 위한 별도 메타‑트랙(예: P‑0)을 정의해 완충을 두는 편이 좋아 보입니다.
- WorldService를 정책/승급/할당 SSOT로 더 강하게 중앙집중화하는 것은 단순성을 높이지만, 팀·조직 관점에서는 병목이 될 위험이 있어, 내부를 policy engine / allocation engine / evaluation pipeline 같은 서브 도메인으로 나누고 책임을 위임할 수 있게 설계하는 보완이 필요해 보입니다.
- NodeID CRC 불일치 시 무조건 400으로 거절하는 전략은 규약을 강하게 enforce하는 대신, 마이그레이션·버전업·실수 상황에서 운영자 경험이 거칠어질 수 있으므로, 에러 메시지와 self‑heal 전략(자동 재계산, 마이그레이션 도구 등)을 함께 정의하는 쪽이 안전해 보입니다.
- “신 방식이 하나라도 준비되면, 구 방식 deprecation 타이머 시작” 원칙은 유지하되, history_provider → world/preset 전환 같은 대표 케이스에 대해서는 마이그레이션 가이드, 자동 변환 스크립트, lint 규칙 등을 로드맵 레벨에서 같이 정의해 두면 실제 도입 비용을 줄일 수 있을 것 같습니다.
- ValidationPipeline vs WorldService 책임 재분배 설계에서는 “형식/스키마 검증”, “정책/리스크 검증”, “환경/리소스 검증”처럼 층위를 나눠, 무엇이 어디의 SSOT인지 표로 고정해 두면 이후 리뷰 기준으로 쓰기 좋을 것 같습니다.
- default‑safe(모호하면 backtest/compute‑only) 규칙은 기본값으로 적절하지만, 의도적으로 위험을 감수하고 live를 여는 고급 운영 플로우에 대해서는 별도의 override 절차(명시적 플래그 + 감사 로그 + 2‑인 승인 등)를 설계해 두는 것도 고려할 만해 보입니다.

⸻

의견2. 실행 가능성 보강 관점 코멘트

- 방향(SSOT 명확화, 수직 슬라이스 중심, 책임 단순화)은 적절하지만, 실행 계획이 헐거워 완료 게이트와 위험 관리를 추가해야 합니다.
- 프로그램별 P0 완료 기준(SubmitResult 스키마, WS 정책 강제 여부, CLI/문서 반영 등)과 담당/일정을 명시해 “끝났는지” 판단 가능하게 해야 합니다.
- 강한 규약(ExecutionDomain 중앙화, NodeID 불일치 400, cross‑domain cache 금지)에는 모니터→warn→fail 단계적 롤아웃과 마이그레이션/롤백 플랜을 함께 두는 것이 안전합니다.
- 호환성·전환 계획이 없으면 기존 사용자 파손 위험이 큽니다. deprecation 타임라인, 마이그레이션 가이드·도구, 린트/자동 변환 경로를 로드맵에 포함시키세요.
- ValidationPipeline 슬리밍은 “어떤 필드/검증을 유지·제거하고, 대체는 어디서?”를 스키마 수준으로 박아야 후속 PR 리뷰 기준이 생깁니다.
- P‑C의 골든 시그널은 최소 세트(예: submit→warm‑up 지연, WS 결정 지연, 라이브 승급 지연)와 SLO, 대시보드/알람 위치까지 정의해야 관측 가능성이 생깁니다.

⸻

의견4. 코드베이스 현황 대조 및 타당성 검증 (GitHub Copilot)

### 1. 현황 분석 및 문제점 검증

제안서에서 지적한 핵심 문제점들이 실제 코드(`qmtl`)에 존재함을 확인했습니다.

*   **이중 진실 (SSOT 위반) 확인**:
    *   **Runner vs WorldService**: `qmtl/sdk/runner.py`의 `Runner.submit` 및 `_postprocess_result` 메서드를 보면, `execution_domain`이 "shadow"일 때 주문을 건너뛰는 로직이 SDK 내부에 하드코딩되어 있습니다. 이는 실행 정책(Policy)이 `WorldService`에 중앙화되지 않고 SDK로 누수된 전형적인 예시입니다.
    *   **ValidationPipeline**: `Gateway`의 `SubmissionPipeline`과 `WorldService`의 `policy_engine.py`가 각자 검증 및 컨텍스트 생성 로직을 가지고 있어, "이 전략이 실행 가능한가?"에 대한 판단 주체가 분산되어 있습니다.

*   **"Paved Road"의 부재**:
    *   `qmtl/examples/strategies/general_strategy.py`를 보면, 사용자가 `QuestDBHistoryProvider`와 `dsn`을 직접 인스턴스화하여 주입하고 있습니다.
    *   제안서의 지적대로, 일반 사용자가 인프라 연결 정보(DSN)를 직접 다루는 것은 "Core Loop" 경험을 저해합니다. `world` 설정만으로 데이터 파이프라인이 자동 연결되는(Auto-wiring) 구조가 필수적입니다.

*   **모호한 실행 모드**:
    *   `Runner.submit`의 시그니처가 `mode: Mode | str`을 받고 있으며, 이를 기반으로 `resolve_execution_context`가 복잡한 플래그(`offline_requested`, `force_offline` 등)를 계산합니다. 이는 사용자의 의도(User Intent)와 시스템의 실제 실행 상태(Runtime State)가 명확히 분리되지 않은 상태입니다.

### 2. 개선 방향(P-A, P-B, P-C)의 타당성

제안된 3개의 프로그램(Vertical Slice) 중심 접근은 기술적 부채를 해소하고 제품 가치를 전달하는 데 매우 효과적인 전략입니다.

*   **P-A (Core Loop Paved Road v1)**: **[최우선 순위]**
    *   가장 시급합니다. `Runner.submit(strategy, world="crypto")` 한 줄로 백테스트부터 배포 판단까지 끝나는 경험을 완성해야 합니다.
    *   이를 위해 `Runner`에서 도메인 판단 로직을 제거하고, `WorldService`가 반환하는 `DecisionEnvelope`를 따르도록 변경하는 것은 필수적입니다.

*   **P-B (Promotion & Live Safety)**:
    *   현재 `Runner`가 `live` 모드를 요청할 수 있는 구조는 위험합니다. 라이브 승급은 반드시 `WorldService`의 정책과 2-Phase Apply(Freeze -> Switch)를 통해서만 이루어져야 한다는 원칙은 시스템 안정성을 위해 타협할 수 없는 부분입니다.

*   **P-C (Data Autopilot)**:
    *   `Seamless`가 이미 준비되어 있음에도 `examples`에서 활용되지 못하는 점을 해결해야 합니다. 데이터 품질과 백필 책임을 사용자에게서 플랫폼으로 가져오는 올바른 방향입니다.

### 3. 추가 제언 및 보완점

제안서 하단의 의견(Opinion 1, 2)을 포함하여, 실행 단계에서 고려해야 할 점들입니다.

1.  **마이그레이션 전략의 구체화 (Opinion 1 지지)**:
    *   `history_provider` 직접 주입 방식을 `deprecated` 처리할 때, 기존 코드를 `world` 기반으로 변환해주는 가이드나 도구가 없으면 사용자 저항이 클 것입니다.
    *   **NodeID Determinism**: NodeID 계산 로직이 바뀌면 기존에 저장된 데이터나 상태와 불일치가 발생할 수 있습니다. 이에 대한 마이그레이션 경로(예: 버전별 해시 허용 또는 일괄 마이그레이션 툴)가 로드맵에 포함되어야 합니다.

2.  **WorldService의 복잡도 관리**:
    *   모든 정책을 `WorldService`로 모으면 `WorldService`가 거대한 모놀리스(Monolith)가 될 위험이 있습니다. 내부적으로 `PolicyEngine`(판단), `AllocationService`(자원 배분), `PromotionManager`(승급 절차) 등으로 모듈을 잘 격리해야 합니다.

3.  **CI/CD Gate (Opinion 2 지지)**:
    *   "Core Loop 계약 테스트"는 매우 좋은 아이디어입니다. `tests/e2e/core_loop`에 "전략 제출 -> 승인 -> 배포" 시나리오를 검증하는 테스트를 먼저 작성하고, 이 테스트가 통과하는 것을 P-A 프로그램의 완료 조건(Definition of Done)으로 삼아야 합니다.

### 결론

이 문서는 현재 QMTL 프로젝트가 직면한 구조적 한계를 정확히 짚고 있으며, 이를 해결하기 위한 **"수직적 통합(Vertical Slice)" 접근법은 매우 타당합니다.**

단순히 모듈을 리팩토링하는 것이 아니라, **"사용자 경험(Runner.submit)"을 기준으로 아키텍처를 재정렬**하려는 시도는 프로젝트의 성숙도를 높이는 데 결정적일 것입니다. 이 로드맵대로 진행하는 것을 강력히 권장합니다.

⸻

의견3. 아키텍처 문서 기반 타당성 검토 (GitHub Copilot)

### 1. 문제 진단의 정확성 ✅

제안 문서가 짚은 문제점은 실제 아키텍처 문서들(`architecture.md`, `gateway.md`, `worldservice.md`, `core_loop_roadmap.md`)을 검토한 결과 **대부분 타당합니다**:

| 제안 문서의 지적 | 실제 상태 | 판정 |
|---|---|---|
| As-Is/To-Be 혼재 | `architecture.md`, `gateway.md`, `worldservice.md` 모두 As-Is/To-Be 섹션이 존재하며, 구현 상태가 문서마다 다름 | ✅ 정확 |
| ValidationPipeline vs WorldService 이중 진실 | `worldservice.md` §0-A에서 "두 레이어가 모두 weight/contribution 개념을 가져 혼동 여지"라고 명시 | ✅ 정확 |
| ExecutionDomain 결정 권한 분산 | `gateway.md`에서 "제출 메타의 execution_domain 힌트와 WS 결정이 동시에 존재하지만 충돌/우선순위가 흩어져 있음"이라고 인정 | ✅ 정확 |
| history_provider 직접 구성 vs Seamless preset 혼재 | `architecture.md` §0.1.1-0.1.2에서 "world만 주면 Seamless가 자동 붙는다"는 계약이 없다고 명시 | ✅ 정확 |

### 2. 제안된 3개 프로그램(P-A/B/C) 구조의 타당성 ✅

**기존 T1-T6 트랙의 한계:**
- `core_loop_roadmap.md`의 T1-T6은 모듈별 분류(SDK, WS, Seamless, Gateway 등)로 구성
- 이는 **수평적 레이어 개선**에 적합하지만, Core Loop 전체를 관통하는 **수직적 기능 완성**을 보장하기 어려움

**P-A/B/C 프로그램 구조의 장점:**
- **P-A (Core Loop Paved Road)**: 신규 사용자가 즉시 경험할 "황금 경로" 구축에 집중
- **P-B (Promotion & Live Safety)**: backtest→live 승급 안전성에 집중
- **P-C (Data Autopilot & Observability)**: 데이터/관측에 집중

이 구조는 `architecture.md`의 North Star("전략 로직에만 집중하면 시스템이 알아서 최적화")와 **직접적으로 정렬**됩니다.

### 3. 핫스팟 5곳 분석의 정확성

| 핫스팟 | 제안 문서의 "과감한 대응" | 기존 문서 상태 | 타당성 |
|---|---|---|---|
| **4.1 ValidationPipeline vs WS** | VP를 지표 계산+sanity check로 축소, WS만 정책/게이팅 담당 | `worldservice.md` To-Be와 일치 | ✅ |
| **4.2 ExecutionDomain 힌트 제거** | Runner에서 mode는 "사용자 기대" 수준, 실제 도메인은 WS만 결정 | `gateway.md` S6에서 이미 "WS 결정 우선"을 명시하나 코드 경로 제거는 미완 | ✅ |
| **4.3 history_provider vs Seamless preset** | world 설정만으로 Seamless 자동 구성 | `architecture.md` To-Be에서 동일한 방향 제시 | ✅ |
| **4.4 TagQuery NodeID 결정성** | NodeID CRC 파이프라인 필수화, 동일 query spec→동일 NodeID 보장 | `architecture.md` Determinism Checklist에 이미 포함 | ✅ |
| **4.5 WS와 Core Loop 연결** | SubmitResult에 WS 평가/활성 요약을 1급 구성요소로 포함 | `core_loop_roadmap.md` T1-M1과 정확히 일치 | ✅ |

### 4. 잠재적 우려 사항

#### 4.1 "소극적 대응 방지" 운영 장치의 실현 가능성 ⚠️

제안 문서는 다음을 제안합니다:
- ADR + Program 태깅
- "신 방식 준비 시 구 방식 deprecation 타이머 시작"
- Core Loop 계약 테스트를 CI Gate로

**우려**: 이미 `.github/copilot-instructions.md`와 `AGENTS.md`에 복잡한 CI 파이프라인이 정의되어 있습니다. 추가적인 Program 태깅 시스템은 **오버헤드**가 될 수 있습니다.

**권장**: ADR 태깅보다는 **Core Loop 계약 테스트 스위트(P0-T6-M1)를 우선** 구현하고, 이 테스트가 CI Gate가 되면 자연스럽게 방향성이 강제됩니다.

#### 4.2 P-A의 P0 범위가 매우 넓음 ⚠️

P-A의 P0만 해도:
- P-A-1: SubmitResult ↔ WS Envelopes 정렬
- P-A-2: ExecutionDomain 결정 권한 WS로 100% 이동
- P-A-3: world/preset 기반 Seamless auto-wiring
- P-A-4: 예제/문서 재작성

**우려**: 이 4개를 동시에 P0로 진행하면 scope creep 위험이 있습니다.

**권장**: P-A-1과 P-A-2를 **진정한 P0**로, P-A-3과 P-A-4는 **P1**로 재분류하는 것이 현실적입니다. SubmitResult/ExecutionDomain 정렬이 완료되어야 Seamless auto-wiring과 문서 개편이 의미 있기 때문입니다.

### 5. 결론 및 권장 사항

**전반적 타당성: ✅ 높음**

이 제안은 기존 `core_loop_roadmap.md`의 **구조적 약점(모듈별 분류로 인한 국지적 최적화 위험)**을 정확히 짚고, **End-to-End 수직 슬라이스 기반 프로그램 구조**로 전환을 제안합니다. 이는 기존 아키텍처 문서들의 To-Be 방향과 일치합니다.

**실행 권장 순서:**

1. **즉시**: `core_loop_roadmap.md` 상단에 P-A/B/C 프로그램 섹션 추가
2. **1단계**: P-A-1 (SubmitResult 정규화) + P-A-2 (ExecutionDomain 중앙화) 집중
3. **2단계**: Core Loop 계약 테스트 스켈레톤 (`tests/e2e/core_loop`) 작성 → CI Gate화
4. **3단계**: ValidationPipeline 슬리밍 ADR 작성

**한 가지 조정 제안**: P0 범위를 현실적으로 축소하고, "신 방식 준비 시 구 방식 deprecation" 원칙은 이미 `architecture.md`에 명시된 "단순성 > 하위 호환성" 원칙과 통합하여 별도 운영 장치보다는 **기존 원칙의 강화**로 접근하는 것이 좋겠습니다.



---------------------------------
의견 1~4에 대한 종합 평가


먼저 결론부터 말하면, 의견 1~4는 서로 상충하지 않고, 기존 설계 제안의 방향성을 유지한 채 “실행 가능성·운영 가능성·마이그레이션 현실성”을 보강하는 성격입니다. 일부는 강도를 조정하거나 범위를 재구성하는 것이 좋아 보이지만, 전반적으로 수용 가치가 높은 보완점들입니다.

아래에서 의견별로 타당성을 정리하고, 그걸 종합했을 때 어떤 식으로 로드맵/설계에 반영하는 게 합리적인지 정리하겠습니다.

⸻

1. 의견1에 대한 평가

의견1의 핵심 포인트는:
	1.	P‑A/B/C 프로그램 구조는 유지하되, “어느 프로그램에도 속하지 않는 변경은 거부” 규칙은 과도할 수 있으니 P‑0 같은 메타‑트랙을 두자.
	2.	WorldService를 SSOT로 더 강하게 세우는 것은 맞지만, 내부적으로는 서브 도메인(Policy / Allocation / Evaluation 등)으로 쪼개 병목을 완화해야 한다.
	3.	NodeID CRC 불일치 시 무조건 400 전략은 강하지만, 운영 경험을 위해 에러 메시지와 self‑heal 전략이 함께 있어야 한다.
	4.	“신 방식 준비 시 구 방식 deprecation 타이머 시작” 원칙은 유지하되, 마이그레이션 가이드·자동 변환 도구·lint 등을 로드맵 레벨에서 같이 정의해야 한다.
	5.	ValidationPipeline vs WorldService 책임 재분배는 검증 층위(형식/정책/환경)로 나눠 표로 고정하면 좋다.
	6.	default‑safe 원칙은 유지하되, 고급 운영 플로우용 override 절차(명시 플래그 + 감사 로그 + 2‑인 승인 등)를 별도로 설계할 필요가 있다.

타당성 판단:
	•	(1) P‑0 메타‑트랙 제안
이건 매우 현실적인 보완입니다. “프로그램 외 변경은 금지”를 그대로 적용하면, 공통 인프라/관측 개선까지 억지로 프로그램에 끼워 넣는 부작용이 생깁니다.
→ “모든 변경은 P‑A/B/C 또는 P‑0(플랫폼/공통 인프라)에 속해야 한다”로 완화하는 것이 합리적입니다.
	•	(2) WorldService 내부 서브 도메인 분리
외부에서 볼 때는 WS가 정책·승급·할당 SSOT로 보이되, 내부적으로는 책임이 분할되어야 병목/조직적 부담을 줄일 수 있습니다. Core Loop에서 WS를 더 강하게 세우겠다는 원래 방향과도 충돌하지 않습니다.
→ WS 설계 문서에 “외부 SSOT / 내부 서브 도메인” 구조를 추가하는 게 좋겠습니다.
	•	(3) NodeID CRC 400 + self‑heal
최종 상태(long‑term)에서 규약 위반은 hard fail(400)이 맞습니다. 다만 도입·마이그레이션 단계에서 바로 400으로 가면 운영자가 상당한 마찰을 겪습니다.
→ 의견2에서 말한 단계적 롤아웃(모니터→warn→fail)과 결합해서,
	•	초기에 “불일치 감지 + 자동 재계산 + 경고 로그/메트릭”
	•	안정화 후 hard fail 전환
식으로 설계하는 게 타당합니다.
	•	(4) Deprecation + 마이그레이션 도구
“단순성 > 하위 호환성” 원칙을 실제로 적용하려면, 사용자를 끊어내는 것이 아니라 “옮기기 쉽게 만들어 준 뒤 끊는 것”이 필요합니다. history_provider → world/preset 전환, ValidationPipeline 슬리밍 등 핵심 변경에는 반드시 동반되어야 하는 요구입니다.
	•	(5) ValidationPipeline 층위 분리 표
ValidationPipeline vs WorldService 책임 재분배를 리뷰/PR 레벨에서 반복 논쟁하지 않으려면,
	•	“이 검증은 형식/스키마이므로 VP SSOT”
	•	“이 검증은 정책/리스크이므로 WS SSOT”
같은 표를 한 번 박아두는 게 유효합니다. 이건 설계/문서 수준 최적화로서 타당합니다.
	•	(6) default‑safe override
운영 현실을 생각하면 “위험을 감수하고 live를 열어야 하는 순간”을 완전히 배제하기 어렵습니다.
다만, 이걸 “일반적인 옵션”이 아니라 “break‑glass flow”로 두는 것이 중요합니다.
→ 제안된 것처럼 명시 플래그 + 감사 로그 + 2‑인 승인 등 friction을 충분히 크게 두면, 기본 원칙을 훼손하지 않으면서도 예외를 수용할 수 있습니다.

요약:
의견1은 “원래 제안의 방향성을 유지하면서, 운영/조직 현실을 반영해 경직된 규칙을 완충하는” 성격입니다. 대부분 수용하는 것이 좋고, default‑safe override는 “극히 제한된 비상 플로우”로 명시하는 정도의 보정만 필요해 보입니다.

⸻

2. 의견2에 대한 평가

의견2의 핵심은 “실행 계획을 더 구체적으로 만들고, 위험을 통제할 수 있게 하자”입니다.

주요 포인트:
	1.	방향은 맞지만, 프로그램별 P0 완료 기준과 담당/일정이 명확하지 않다.
	2.	강한 규약(ExecutionDomain 중앙화, NodeID 400, cross‑domain cache 금지)은 모니터→warn→fail 식 단계적 롤아웃과 마이그레이션/롤백 플랜이 필요하다.
	3.	호환성과 전환 계획(deprecation 타임라인, 마이그레이션 가이드, lint/자동 변환)이 없으면 기존 사용자 파손 리스크가 크다.
	4.	ValidationPipeline 슬리밍은 “어떤 필드/검증을 유지·제거·위임할지”를 스키마 수준으로 정의해야 PR 리뷰 기준이 생긴다.
	5.	P‑C 골든 시그널은 최소 세트 + SLO + 대시보드/알람 위치까지 정의해야 관측 가능성이 생긴다.

타당성 판단:
	•	(1) P0 완료 기준/담당/일정
원래 제안은 “무엇을 해야 하는지”는 잘 기술되어 있지만, “언제/어떻게 이걸 done으로 볼지”는 다소 추상적입니다.
→ P‑A/P‑B/P‑C 각각에 대해 P0 Definition of Done을 명시하고, 담당자/목표 시점 정도는 로드맵에 추가하는 게 필요합니다.
	•	(2) 강한 규약의 단계적 롤아웃
이 부분은 의견1의 NodeID self‑heal 논의와도 완전히 합치됩니다. ExecutionDomain 중앙화, cross‑domain cache 금지 등도 동일하게 적용해야 하는 원칙입니다.
→ “새 규약 도입 = 곧바로 hard fail”이 아니라,
	•	1단계: 측정/메트릭
	•	2단계: warn/로그 + 옵트인 fail
	•	3단계: 디폴트 hard fail
로 나누는 설계가 타당합니다.
	•	(3) 호환성/전환 계획
이 역시 의견1과 맥락이 같고, 제거/슬리밍/중앙화 작업에는 필수 요소입니다. 특히 QMTL이 이미 사용 중인 환경이라면, 이걸 빼고 갈 수는 없습니다.
	•	(4) ValidationPipeline 슬리밍의 스키마화
“VP에서 정책을 뺀다” 수준으로는 실제 개발 때 계속 경계가 흔들립니다. 어떤 필드/검증이 어디에 귀속되는지 스키마/테이블로 명시해야 합니다.
→ 이후 PR 리뷰에서 “이 검증은 VP에 두면 안 된다”를 기계적으로 판단할 수 있는 기준이 생깁니다.
	•	(5) P‑C 골든 시그널 구체화
“골든 시그널이 있어야 한다”에서 한 발 더 나아가,
	•	최소 지표 세트(예: submit→warm‑up, WS 결정 지연, live 승급 지연, 데이터 취득 실패율 등)
	•	각 지표의 SLO
	•	시각화/알람 위치
를 로드맵에서 정의하는 것은 의미 있습니다.

요약:
의견2는 방향성이라기보다 “이걸 실제로 굴러가게 만들려면 필요한 실행·롤아웃·거버넌스 요소”를 잘 짚고 있습니다. 제안한 보완점들은 원래 설계와 충돌하지 않고, 그대로 얹어가는 게 좋습니다. 다만 팀 규모/속도에 맞춰 문서화와 프로세스 강도를 적절히 조절할 필요는 있습니다.

⸻

3. 의견4에 대한 평가 (코드베이스 현황 대조)

의견4는 실제 코드 구조(라고 제시된 내용)를 근거로:
	•	Runner와 WorldService 사이의 정책/도메인 결정 중복,
	•	ValidationPipeline와 WS 정책 엔진 사이의 이중 진실,
	•	예제 코드에서 history_provider를 직접 주입하는 패턴,
	•	Runner.submit의 mode/플래그 혼잡,

을 확인했다고 주장합니다. 그리고 이를 근거로:
	•	SSOT 위반 문제 제기가 정당함,
	•	“Paved Road 부재” 지적이 실제 코드와 일치함,
	•	P‑A를 최우선 순위로 두어야 한다,

는 결론을 내립니다.

타당성 판단:
	•	우리가 지금 보고 있는 건 “코드 스니펫 자체”가 아니라 “코드에 이런 내용이 있었다”는 서술입니다.
하지만, 이 서술 내용은 기존 아키텍처 문서에 나온 As‑Is 묘사와 논리적으로 잘 맞습니다.
	•	Runner가 shadow 모드에서 주문 패스를 갖고 있을 법하다.
	•	Gateway와 WS 양쪽에 검증/컨텍스트 생성이 있는 상태라는 설계 설명이 이미 있었다.
	•	예제에서 직접 provider/DSN을 구성하고 있는 패턴은, 문서에서 지적된 “사용자가 인프라 디테일을 알고 있어야 한다”는 문제와 일치.
	•	따라서 “현재 코드가 정말 저러냐”를 별도로 검증하진 못하더라도,
문서 + 기존 문제 인식과 일관된 정합적인 서술입니다.
이 서술이 옳다면, 제안한 방향(WS SSOT화, P‑A 우선, history_provider → world/preset)은 더더욱 강하게 정당화됩니다.
	•	의견4가 추가로 제안하는:
	•	“P‑A를 최우선 순위로 둘 것”
	•	“Core Loop 계약 테스트를 P‑A의 DOD로 삼을 것”
도 원래 제안과 의견2의 “CI Gate” 아이디어와 맞물려 자연스러운 확장입니다.

요약:
의견4는 “지금 제안이 현실의 코드와 맞지 않다”가 아니라, “코드 상태를 보면 이 제안이 꼭 필요하다”는 방향의 검증입니다. 논리 구조상 무리가 없고, 기존 설계 문서 서술과도 일치하므로, 제안의 타당성을 뒷받침하는 자료로 보는 것이 합리적입니다.

⸻

4. 의견3에 대한 평가 (아키텍처 문서 기반 검증)

의견3은 아키텍처 문서를 근거로:
	•	As‑Is/To‑Be 혼재,
	•	ValidationPipeline vs WorldService 이중 진실,
	•	ExecutionDomain 결정 권한 분산,
	•	history_provider vs Seamless preset 혼재,

등이 실제 문서에서 이미 인정하고 있는 문제임을 표로 정리해 “문제 진단 자체는 정확하다”고 검증합니다.

그리고 추가로:
	1.	P‑A/B/C 구조가 기존 T1–T6의 “수평 트랙” 한계를 보완하는 수직 통합 구조라 타당하다.
	2.	핫스팟 5곳(ValidationPipeline, ExecutionDomain, history_provider, TagQuery/NodeID, WS–Core Loop 연동)에 대한 “과감한 대응”이 기존 문서의 To‑Be와 일치한다.
	3.	다만:
	•	ADR + Program 태깅 등 프로세스가 과도할 수 있으니, Core Loop 계약 테스트를 CI Gate로 삼는 것부터 우선하자.
	•	P‑A의 P0 범위(P‑A‑1..4)가 너무 넓어 scope creep 위험이 있으니, P‑A‑1/2를 진정한 P0로, P‑A‑3/4는 P1로 재분류하자.

타당성 판단:
	•	1, 2는 사실상 “문서적으로 이미 인정한 문제/향후 방향”을 다시 확인하는 것이므로, 설득력이 충분합니다.
	•	ADR + Program 태깅 vs Core Loop 테스트 Gate:
	•	두 가지는 상호 배타가 아니라 보완 관계이지만, 우선 순위 관점에서 보면 “E2E 계약 테스트를 먼저 CI에 심는 것”이 더 직접적인 품질 보증 수단인 것은 맞습니다.
	•	현재 팀의 프로세스 복잡도를 감안하면, ADR 시스템을 지나치게 무겁게 가져가기보다는,
	•	PR 설명에 “연결 프로그램/트랙”만 명시
	•	중요한 의사결정에 한해 ADR 작성
정도로 경량화하고, CI Gate는 테스트 기반으로 거는 것이 현실적입니다.
	•	P‑A P0 범위 축소:
	•	P‑A‑1: SubmitResult ↔ WS Envelopes 정렬
	•	P‑A‑2: ExecutionDomain 결정 권한 WS로 100% 이동
	•	P‑A‑3: world/preset 기반 Seamless auto‑wiring
	•	P‑A‑4: Paved Road 기준으로 예제/문서 재작성
을 한 번에 P0로 잡으면, 실제로는 P‑A가 “절대 안 끝나는 프로젝트”가 될 위험이 큽니다.
	•	Core Loop 경험을 똑바로 세우는 “기초 공사”는 P‑A‑1/2에 있습니다. P‑A‑3/4는 그 위에 올라가는 UX/데이터 자동화/문서 레이어입니다.
→ P‑A‑1/2를 P0로, P‑A‑3/4를 P1로 재분류하자는 의견은 실행 관점에서 매우 타당합니다.

요약:
의견3은 문제 진단의 정당성을 문서로 다시 확인해 주고, 프로세스와 범위 조정에 대해 현실적인 제안(P‑A P0 축소, 테스트 기반 Gate 우선)을 합니다. 그대로 수용하는 것이 좋아 보입니다.

⸻

5. 종합 의견: 어떻게 정리해서 가져가면 좋은지

위 네 개 의견을 통합하면, 현재 architecture_roadmap_redesign.md에 반영해야 할 “정리된 방향”은 대략 다음과 같습니다.
	1.	프로그램 구조
	•	P‑A/B/C라는 수직 프로그램 구분은 그대로 유지.
	•	여기에 P‑0 (플랫폼/공통 인프라/관측) 메타‑트랙을 추가.
	•	모든 변경은 P‑A/B/C 또는 P‑0 중 최소 하나에 매핑되도록 요구하되, “프로그램에 속하지 않으면 무조건 거부”처럼 경직되게 쓰지는 않는다.
	2.	우선순위 및 P0 범위 재조정
	•	최우선 프로그램은 P‑A (Core Loop Paved Road v1).
	•	P‑A의 진정한 P0는:
	•	P‑A‑1: SubmitResult ↔ WS Envelopes 정렬
	•	P‑A‑2: ExecutionDomain 결정 권한 WS로 100% 이동
	•	P‑A‑3(Seamless auto‑wiring), P‑A‑4(문서/예제 정리)는 P‑A P1로 승격.
	•	P‑B, P‑C는 P‑A‑1/2 기반 위에서 진행하되, 자본/라이브 리스크가 크다면 P‑B의 일부(2‑Phase Apply skeleton, cross‑domain cache 금지 모니터링)는 P‑A‑2와 병렬로 P0 수준에 일부 끌어올릴 수 있음.
	3.	SSOT 강화 & 책임 재분배
	•	ValidationPipeline:
	•	정책/게이팅 개념 제거, 지표 계산 + 로컬 sanity check로 축소.
	•	“형식/스키마 / 정책/리스크 / 환경/리소스 검증” 층위 표를 만들어 어떤 검증이 어디 SSOT인지 명시.
	•	WorldService:
	•	외부적으로는 정책/승급/할당 SSOT.
	•	내부적으로는 PolicyEngine / EvaluationPipeline / AllocationEngine 등 서브 도메인으로 설계.
	•	ExecutionDomain:
	•	Runner/SDK의 mode는 사용자 기대 표현에 국한.
	•	실제 execution_domain은 항상 WS effective_mode에서 파생.
	•	history_provider:
	•	공식 템플릿/guides에서는 world/preset 기반 Seamless auto‑wiring을 기본 경로로.
	•	직접 history_provider를 주입하는 패턴은 “고급/실험”으로 격하 + deprecation 타이머 및 마이그레이션 가이드 준비.
	4.	규약 도입/변경에 대한 롤아웃 전략
	•	ExecutionDomain 중앙화, NodeID CRC 규약, cross‑domain cache 금지 등 강한 규약은 공통적으로:
	1.	관측/메트릭 단계
	2.	warn + 옵트인 fail 단계
	3.	디폴트 hard fail 단계
의 3단계 롤아웃을 로드맵에 명시.
	•	NodeID의 경우, 불일치 감지 시:
	•	상세 에러 메시지
	•	필요시 자동 재계산/마이그레이션 도구 제공
	•	최종적으로는 400으로 수렴
	5.	마이그레이션/호환성 전략
	•	각 핵심 변경(ValidationPipeline 슬리밍, history_provider → world/preset, ExecutionDomain 중앙화, NodeID 규약 강화)에 대해:
	•	deprecation 타임라인
	•	마이그레이션 가이드
	•	가능하다면 자동 변환/린트 규칙
을 로드맵 상에 함께 정의.
	6.	계약 테스트와 CI Gate
	•	tests/e2e/core_loop에 Core Loop 계약 테스트 스켈레톤부터 작성:
	•	“전략 작성 → Runner.submit → WS 평가 → Activation → (가짜) 자본 배분” 수직 슬라이스.
	•	이 테스트 세트가 P‑A P0의 핵심 DOD가 되도록 하고, 이후 CI에서 Gate로 사용.
	•	ADR + Program 태깅은 이보다 한 단계 낮은 강도의 거버넌스로 두되,
	•	“중요한 아키텍처 결정에만 ADR 필수”
	•	PR 템플릿 수준에서 “프로그램/트랙” 필드 요구
정도로 현실적인 무게로 운영.
	7.	관측(Observability) 구체화
	•	P‑C에서 정의할 골든 시그널 최소 세트와 SLO, 대시보드 위치를 로드맵에 명기:
	•	예: submit→warm‑up 지연, WS 결정 지연, live promotion latency, Seamless 데이터 실패율 등.
	8.	default‑safe + break‑glass override
	•	기본 규칙: 애매하면 무조건 backtest/compute‑only.
	•	예외(의도적 위험 감수)는:
	•	명시적인 override 플래그
	•	감사 로그
	•	2‑인 승인/운영상 절차
를 요구하는 별도의 운영 플로우로 정의.

⸻

6. 한 줄로 요약하면

의견1~4는 기존 설계 제안의 방향을 부정하는 것이 아니라,
“수직 프로그램 구조는 유지하되, P‑A P0를 더 작게 정의하고, SSOT와 규약을 강하게 가져가면서도 마이그레이션·운영·관측·거버넌스를 현실적으로 설계하라”는 쪽으로 수렴합니다.

그 방향으로 architecture_roadmap_redesign.md를 한 번 더 리팩터링하면,
지금 문서는 “문제 진단 + 방향성 선언”에서 “실제로 실행 가능한 로드맵”에 더 가까운 상태가 될 것입니다.

⸻

추가 의견(실행 모드 전환 전, 문서에 명문화할 4가지)

- P‑A P0 완료 체크리스트: SubmitResult↔WS 스키마 정렬, ExecutionDomain WS 단일화, core_loop 계약 테스트 스켈레톤 통과, 문서/CLI 반영 여부를 P‑A P0 DOD로 고정.
- 책임자/기한: P‑A/B/C(+P‑0) 각 P0/P1에 DRI와 목표 릴리스/주차를 지정해 “언제 끝나는지” 명시.
- 롤아웃 단계 표: ExecutionDomain 중앙화, NodeID 규약, cross‑domain cache 금지, history_provider deprecation 등에 대해 관측→warn→fail 3단계와 전환 타임라인을 한 표로 정리.
- 마이그레이션 패키지: 각 deprecation 항목별로 가이드 + 자동 변환/린트 유무를 함께 명시해 기존 사용자 파손 위험을 줄이기.
