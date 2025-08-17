# Idea
📌 시장 미시 구조 이론: 잠재 유동성 임계 재구성 이론 (Latent Liquidity Threshold Reconfiguration Theory)

⸻

🏛 이론 개요

이 이론은 **호가창에 드러난 유동성(visible liquidity) 외에도 시장에는 전략적으로 숨겨진 잠재 유동성(latent liquidity)**이 존재하며,
이 유동성은 참여자들이 시장 위험을 재평가하거나 가격이 특정 임계 수준에 도달할 때 일시적으로 나타났다 사라지는 구조적 특징을 가진다고 봅니다.
잠재 유동성은 연속적인 구조가 아니며, **시장 상황에 따라 급격히 재구성(reconfigure)**되며, 이때 가격 반응이 선형에서 비선형으로 전이됩니다.

⸻

📈 비선형 퀀트 알파 생성 응용
	1.	잠재 유동성 재구성 지표 (LLRTI: Latent Liquidity Reconfiguration Threshold Index)
LLRTI_t = \sum_{p \in \text{LOB}} \left( \frac{\Delta \text{Order Depth}{p,t}}{\Delta t} \cdot \mathbb{1}{\{ |\Delta P_t| > \delta \}} \right)
	•	특정 가격 수준에서 급격히 유동성이 증가/감소하는 구간을 탐지
	•	가격 변화가 임계치 \delta를 초과한 순간의 주문 변화율을 누적
	2.	비선형 알파 모델
\alpha_t = \theta_1 \cdot \log(1 + LLRTI_t^\gamma) + \theta_2 \cdot \frac{d \text{Execution Imbalance}_t}{dt}
	•	\gamma > 1: 재구성이 임계 수준을 초과하면 알파는 기하급수적으로 증가
	•	실시간 체결 불균형은 방향성 필터 역할

⸻

🔬 관련 이론 및 확장

분야	관련 개념
정보경제학	Hidden liquidity models, informed vs. uninformed traders (Kyle, 1985)
위기이론	Critical threshold models in systemic risk propagation
계산신경과학	Latent activation thresholds in neural firing
계량경제학	구조 전환 모델 (Structural Break Models)


⸻

✅ 실전 응용 시나리오
	•	고빈도 트레이딩: LLRTI가 급등하고 체결 편향이 한 방향으로 몰릴 때 틱 점프 포지션 진입
	•	옵션 전략: 감마가 극단적으로 민감한 구간에서 재구성 신호를 감지해 델타 재조정
	•	유동성 공급 제한: 잠재 유동성이 회수되는 구간에서는 마켓메이킹 위험 축소

⸻

📢 결론

잠재 유동성 임계 재구성 이론은, 시장 구조가 안정적으로 보일 때조차 비가시적 유동성의 출현·붕괴에 따라 급격히 틱 기반 알파 기회가 생성될 수 있다는 사실을 정량화합니다.
이 이론은 유동성 붕괴 감지, 체결 기반 리스크 관리, 옵션 헷지 전략 최적화에 실질적인 고정밀 퀀트 프레임워크를 제공합니다. 🚀

# 개선 알파 제안
아래는 **직전 제안(잠재 유동성 임계 재구성, LLRTI)**을 토대로, 비판적 점검 → 약점 보완 → 생산 배포까지 가능한 개선 알파를 한 번에 제시한 것입니다.
핵심은 (1) ‘임계’ 탐지를 사건 위험도(hazard) 문제로 재정의, (2) 차원·레짐 정규화로 일반화 가능성 향상, (3) 방향 가이팅과 비용-인식(cost‑aware) 스케일링입니다.

⸻

1) 비판적 점검: LLRTI 알파의 잠재적 한계
	1.	식별성(identifiability) 문제
	•	“잠재 유동성 재구성”은 관측 불가능합니다. 단순히 취소율·깊이 변동 같은 관측 가능한 대리 변수를 넣으면 변동성 급증/체결 과열을 뒤늦게 따라잡는 동행 지표가 되기 쉽습니다.
	•	→ **사건 정의(향후 Δ 내 점프/스프레드 폭발)**를 먼저 확정하고 위험도 모델로 접근해야 선행성이 생깁니다.
	2.	누수(look‑ahead)·과최적화 위험
	•	“가격 변화가 임계치 δ 초과 시의 주문 변화율을 누적” 같은 정의는 그 순간의 가격 변화 자체를 조건으로 삼아 라벨 누수를 만들 수 있습니다.
	•	파라미터 \gamma, \theta는 작은 샘플에서 쉽게 과최적화됩니다.
	3.	시장·거래소 이질성 미보정
	•	암호화폐는 틱사이즈, 수수료, 펀딩/청산 메커니즘, 심야/주말 유동성이 천차만별. 단위/스케일 불일치를 보정하지 않으면 **전이력(portability)**이 약합니다.
	4.	실행 가능성(executability) 간과
	•	LLRTI 급등 직후는 보통 유동성 공백입니다. 알파 ≈ 강한 방향성이라 해도 충분히 채워 넣을 수 있는가(체결 가능성), **실행 비용(스프레드+수수료+충격)**을 넘는가가 핵심인데, 원식에는 비용-인식 스케일링이 부재합니다.
	5.	레짐 오염(regime contamination)
	•	이벤트 장세·평온 장세·청산 장세에서 같은 함수를 쓰면 오탐/미탐이 커집니다.

⸻

2) 개선 콘셉트: 위험도(Hazard) 게이팅 + 방향 가이팅 + 비용-인식 스케일링

2.1 사건 정의(라벨링)
	•	점프 사건 J_{t,\Delta} = \mathbb{1}\{ |P_{t+\Delta} - P_t| > \kappa \cdot \widehat{\sigma}_{t,\Delta} \}
	•	방향 라벨 D_{t,\Delta} = \text{sign}(P_{t+\Delta} - P_t)

\Delta는 250–1000ms(초고빈도) 또는 1–5초(LOB 스냅샷 빈도) 등 전략 지평에 맞춰 고정, \kappa는 예: 1.5–2 표준편차.

2.2 특징량(모두 무차원·레짐 정규화)
	•	z_c: 취소 강도 = 최근 \tau_c 윈도우 취소수 / (추가·수정수 + ε) 의 z‑score
	•	z_d: Depth cliff = \max_k \frac{\text{Depth}{k}-\text{Depth}{k+1}}{\Delta p} 의 z‑score
	•	z_r: Requote 지연 = 레벨별 호가 갱신 간격의 로그‑중앙값 z‑score
	•	z_e: 체결 압력 = 최근 \tau_e 초 공격적 체결량 / 패시브 상단 깊이
	•	z_s: 스프레드 상태 = (스프레드/틱사이즈) 의 z‑score
	•	z_o: 주문흐름 불균형(OFI), z_m: 마이크로프라이스 기울기
	•	(선택) z_q: 큐 불균형, z_\eta: 엔트로피(LOB 불확실성)

모든 z‑score는 **EWM(λ)**로 완만히 추정해 지나친 민감도를 방지.

2.3 사건 위험도(점프 발생 확률) 모델

\underbrace{h_t}_{\text{jump hazard}} \;=\; \sigma\!\Big(\n\beta_0 + \beta_1\,\text{softplus}(z_c) + \beta_2\,\text{softplus}(z_d)\n\t•\t\beta_3\,z_r + \beta_4\,\log(1+z_e^+) + \beta_5\,z_s + \beta_6\,|\,\dot{OBI}_t\,|\n\Big)

\t•\t\sigma(\cdot): 시그모이드, 0–1 위험도
\t•\tsoftplus·\log(1+\cdot): 극단값 포화 → 폭주 방지
\t•\t|\dot{OBI}_t|: 주문서 기울기의 가속(전이 신호)

2.4 방향 가이팅(weight)

g_t \;=\; \tanh\!\big(\eta_0 + \eta_1\,z_o + \eta_2\,z_m + \eta_3\,\text{sign}(\text{OFI}_t)\cdot z_e \big)
\t•\t방향성은 주문흐름/마이크로프라이스가 주도, 체결 압력은 가중만 제공

2.5 비용‑인식 스케일링
\t•\t즉시 비용 근사: C_t = \tfrac{\text{Spread}_t}{2} + \text{takerFee} + \widehat{\text{Impact}}_t
\t•\t체결 가능성 \pi_t: 최근 슬리피지/체결률 기반(예: 충족률 EWMA)

2.6 최종 비선형 알파

\boxed{ \;\alpha_t \;=\; \Big(h_t^{\,\gamma} - \tau\Big)_+ \cdot g_t \cdot \pi_t \cdot e^{-\phi\,C_t} \;}
\t•\t(x)_+ = \max(x,0), 게이팅 후 양수 구간만 트레이드
\t•\t\gamma>1: 임계 근방에서 비선형 증폭
\t•\t\tau: 하한 임계값(오탐 억제), \phi: 비용 패널티
\t•\t해석: “점프 위험도가 높고( h_t ), 방향 일치( g_t ), 체결 가능하며( \pi_t ), 비용 대비 메리트가 있는( e^{-\phi C_t} ) 경우에만 크기가 비선형적으로 커지는 알파”

⸻

3) 구현 체크리스트(실전)
	•\t레짐 분기: 변동성·스프레드·시간대(asia/eu/us)로 레짐 태그 → 파라미터 \beta,\eta,\gamma,\tau,\phi를 레짐별 또는 Mixture‑of‑Experts로 추정
\t•\t차원 정규화: 모든 입력은 틱·호가 단위로 무차원화 → 교차거래소·코인 간 전이력↑
\t•\t라벨링 누수 금지: \widehat{\sigma}_{t,\Delta} 추정은 t까지의 정보만 사용
\t•\t호가 샘플링: 이벤트 타임(체결/LOB 변경 시)로 다운샘플 하되, 호가 갱신 지연을 특징량으로 남김
\t•\t치우침 억제: 상하 1% winsorize, EWM/중앙값 평활 + 박스‑카(or tri‑cube) 로컬 기준선

⸻

4) 추정·검증 프로토콜
	1.	Stage‑1 (Hazard): 로지스틱/포아송(또는 Hawkes‑like)으로 h_t 추정
	2.	Stage‑2 (Direction): g_t를 별도 로지스틱(상승/하락)으로 추정
	3.	Walk‑forward CV: 블록드/앵커드 시계열 CV (예: 6개 구간)
	4.	어블레이션: 각 특징 제거 시 AUC/PR, IC, PnL(after‑cost) 변화
	5.	버킷팅 진단: h_t 디사일별 사건 빈도/평균 수익 모노토닉성 검사
	6.	교차시장: 현물/무기한, 상위·중위 코인, 거래소별 분리 → 메타‑분석
	7.	리스크: triple‑barrier 메타‑라벨로 스톱/목표/시간 동시 평가
	8.	취소/수정 지연 쇼크 구간은 체결률/슬리피지 리포트로 별도 로깅

⸻

5) 실행 규칙(예시)
	•\t엔트리: h_t^{\gamma} > \tau AND g_t와 미드프라이스 모멘텀 동의 → 소량 시작, \pi_t 비례 증액
\t•\t스케일링: 목표 포지션 \propto \alpha_t, 단 max leverage·max participation rate 제한
\t•\t엑싯: h_t \downarrow 또는 g_t 반전, 비용·슬리피지 급증 시 즉시 축소
\t•\t인벤토리: 재고 한도·델타 중립(옵션 결합 시)·시장별 넷 익스포저 관리

⸻

6) 수식 요약(한 장)

\\begin{aligned}
&\\textbf{(1) Hazard} && h_t = \\sigma\\!\\big(\\beta_0 + \\beta_1\\,\\text{softplus}(z_c) + \\beta_2\\,\\text{softplus}(z_d) + \\beta_3 z_r + \\beta_4 \\log(1+z_e^+) + \\beta_5 z_s + \\beta_6 |\\dot{OBI}_t| \\big) \\
&\\textbf{(2) Direction} && g_t = \\tanh(\\eta_0 + \\eta_1 z_o + \\eta_2 z_m + \\eta_3 \\text{sign}(\\text{OFI}_t)\\, z_e) \\
&\\textbf{(3) Cost/Fill} && C_t = \\tfrac{\\text{Spread}}{2} + \\text{takerFee} + \\widehat{\\text{Impact}}t,\\quad \\pi_t \\in [0,1] \\
&\\textbf{(4) Alpha} && \\boxed{ \\alpha_t = \\big(h_t^{\\gamma} - \\tau\\big)+ \\cdot g_t \\cdot \\pi_t \\cdot e^{-\\phi C_t} }
\\end{aligned}

⸻

7) 왜 이게 더 나은가?
	•\t선행성 강화: “위험도→방향→실행”의 3단 분리로 동행성/오탐을 줄임
\t•\t전이력↑: 단위 무차원화 + 레짐별 파라미터 → 거래소/종목 변화에도 견고
\t•\t실전성: 비용·체결률을 내재화 → 이론상 알파 ≠ 실전 PnL 간 괴리 축소
\t•\t안정성: softplus/포화 비선형으로 테일 이벤트 과민 반응을 완화

⸻

8) 확장 아이디어(옵션/암호화폐 특화)
	•\t청산(Liquidation) 수급: 파생 오픈이자·청산 체결을 z_e·z_o에 마크(표식)로 결합
\t•\t펀딩·스테이블코인 베이시스: 레짐 태깅에 포함(자금조달비·베이시스 급변)
\t•\tHawkes 마크드: 취소·체결·재호가를 마크드 Hawkes로 공적분해 \Rightarrow h_t 대체

⸻

마무리

위 개선안은 **이론적 직관(잠재 유동성 임계 전이)**를 유지하되, **예측 문제 정의(위험도)**와 **실행 제약(비용·체결률)**을 수식에 내장해 현금흐름으로 연결되는 비선형 알파로 정제했습니다.
원하시면 이 수식을 바로 적용 가능한 **특징량 산출 절차와 백테스트 체크리스트(파라미터 표 포함)**로 더 세분해 드릴게요.

# 전체 설계·구현 패키지
아래는 직전 개선안( Hazard 게이팅 + 방향 가이팅 + 비용·체결 내재화 )을 현업 적용 수준으로 세분화한 전체 설계·구현 패키지입니다.
바로 구현·백테스트·운영까지 이어질 수 있도록 데이터→특징량→라벨링→모델링→시뮬레이션→리스크→모니터링 순서로 정리했고,
초고빈도(LOB/L2, 50–500ms) 버전과 저빈도(1s~1m 캔들 프록시) 버전을 모두 제공합니다.

⸻

0) 핵심 수식(요약)

\boxed{ \alpha_t \;=\; \Big(h_t^{\,\gamma} - \tau\Big)_+ \cdot g_t \cdot \pi_t \cdot e^{-\phi\,C_t} }
	•	h_t: 점프/전이 Hazard(발생확률)
	•	g_t: 방향 가이팅 (주문흐름/마이크로프라이스 기반)
	•	\pi_t: 체결 가능성(충족률) 추정
	•	C_t: 즉시 비용(스프레드/수수료/충격)
	•	\gamma>1, 임계 \tau, 비용 패널티 \phi

⸻

1) 데이터 요건 & 샘플링

(A) LOB/L2 HFT 버전 (권장)
	•	스냅샷: 상·하단 N레벨(예: 10x10), 50–200ms 간격 또는 이벤트타임(LOB 변경 시)
	•	체결 스트림: aggressor flag(매수/매도), 크기, 가격, 타임스탬프(ns~ms)
	•	거래소 메타: 틱사이즈, 최소수량, taker/maker fee, 라운딩 규칙
	•	선물/무기한: 펀딩, 오픈이자(OI), 강제청산 인근 데이터(가능시)

(B) 1s–1m 프록시 버전 (데이터 제약 시)
	•	캔들(OHLCV) + 스프레드 근사(베스트 bid/ask가 없으면 VWAP/체결가 변화로 근사)
	•	OFI 프록시(EMO, tick rule), 마이크로프라이스 근사, 롤링 깊이 프록시(체결량 밀도)

⸻

2) 라벨링(사건 정의)

점프/전이 라벨
J_{t,\Delta} = \mathbb{1}\!\left\{ \frac{|P_{t+\Delta}-P_t|}{\widehat{\sigma}_{t,\Delta}} > \kappa \right\},\quad \kappa \in [1.5,2.5],\;\Delta \in \{0.25s,0.5s,1.0s\}

방향 라벨
D_{t,\Delta} = \text{sign}\!\big(P_{t+\Delta}-P_t\big)

누수 방지: \widehat{\sigma}_{t,\Delta}는 t까지의 데이터만 EWMA로 추정.
레짐 태깅: (변동성·스프레드·시간대)로 레짐 ID 추가 → 이후 파라미터를 레짐별로.

⸻

3) 특징량(무차원·레짐 정규화)

모든 특징을 z-score(EWM 표준화) 또는 틱/스프레드 단위로 정규화합니다.
	•	취소 강도 z_c: z\big(\tfrac{\#cancel}{\#(new+modify)+\epsilon}\big) @윈도우 \tau_c
	•	Depth cliff z_d: z\big(\max_k \frac{\text{Depth}k-\text{Depth}{k+1}}{\Delta p}\big)
	•	Requote 지연 z_r: 레벨별 호가 갱신 간격의 로그-중앙값 z-score
	•	체결 압력 z_e: z\big(\tfrac{\text{AggressiveVol}_{\tau_e}}{\text{TopDepth}+ \epsilon}\big)
	•	스프레드 상태 z_s: z\big(\tfrac{\text{Spread}}{\text{tick}}\big)
	•	OFI/주문흐름 z_o: 표준 OFI 또는 EMO(Lee–Ready 변형) z-score
	•	마이크로프라이스 기울기 z_m: z\big(\tfrac{w\_ask\cdot ask + w\_bid\cdot bid}{w\_ask+w\_bid}-mid\big) 변동률
	•	|\dot{OBI}|: 주문서 기울기(imbalance)의 시간미분 절댓값
	•	(선택) 큐 불균형 z_q: 레벨0 queue size 차이 z-score
	•	(선택) LOB 엔트로피 z_\eta: 레벨별 확률분포의 Shannon entropy z-score

추천 윈도우: \tau_c,\tau_e=1\sim3s, EWM half-life =2\sim5s.

⸻

4) Hazard 모델 h_t

h_t = \sigma\!\Big(
\beta_0 + \beta_1\,\text{softplus}(z_c) + \beta_2\,\text{softplus}(z_d)
	•	\beta_3\,z_r + \beta_4\,\log(1+z_e^+) + \beta_5\,z_s + \beta_6\,|\dot{OBI}_t|
\Big)

	•	모형: 로지스틱 회귀(해석 용이) → 필요시 GBDT/XGBoost 또는 마크드 Hawkes(취소·체결·재호가를 마크로)로 대체
	•	목표: J_{t,\Delta} (binary). 클래스 불균형은 가중치/포칼로스 사용
	•	정규화: L2 + feature clipping(winsorize 1% 양끝)
	•	레짐별 파라미터: \beta(\text{regime})

검증: AUC/PR, calibration curve, 디사일 버킷팅에서 사건 빈도가 단조 증가해야 함.

⸻

5) 방향 가이팅 g_t

g_t = \tanh\!\big(\eta_0 + \eta_1 z_o + \eta_2 z_m + \eta_3 \text{sign}(\text{OFI}_t)\cdot z_e \big)
	•	모형: 로지스틱(상승/하락) 또는 회귀(다음 Δ 수익률)
	•	특징량: OFI, 마이크로프라이스 기울기, 체결 압력(부호), 최근 미드모멘텀
	•	검증: directional accuracy, 업사이드/다운사이드 분리 IC

⸻

6) 비용 C_t & 체결 가능성 \pi_t
	•	C_t = \tfrac{\text{Spread}_t}{2} + \text{takerFee} + \widehat{\text{Impact}}_t
	•	충격 \widehat{\text{Impact}}_t:
	•	(간단) 제곱근 법칙: k \cdot \sigma \sqrt{q/V}
	•	(고급) LOB 기울기 기반: \tfrac{q}{\sum_{k} \text{Depth}_k} + 비선형 보정
	•	체결 가능성 \pi_t \in [0,1]: 최근 N회 시장가/지정가 충족률 EWMA.
	•	지정가 사용 시 큐 포지션/대기열 추정(단순: 레벨0 잔량 대비 주문 비율).

⸻

7) 최종 알파 & 포지션

\alpha_t = \big(h_t^{\gamma} - \tau\big)+ \cdot g_t \cdot \pi_t \cdot e^{-\phi C_t},\quad
w_t = k{\text{risk}} \cdot \alpha_t
	•	\gamma \in [1.5,3], \tau: trade gating(예: 상위 20% hazard만)
	•	\phi: 비용 민감도(0.5~2.0)
	•	사이징: 목표 포지션 w_t (달러/계약), max participation & max leverage 제한

⸻

8) 백테스트(미시구조 인지)

시뮬레이션 엔진
	•	레이지 실행 금지: 엔트리 시 현재 LOB로 체결/부분충족/슬리피지 계산
	•	타임스탬프·지연: 의사결정→전송→수락까지 고정/랜덤 지연(예: 5–20ms)
	•	수수료/리베이트: 거래소별 실측 적용, 펀딩비 포함(파생)
	•	청산/리밸런스: triple‑barrier (목표/손절/타임아웃 Δ)
	•	위험 관리: per‑trade·per‑minute VaR/Drawdown 제한, kill‑switch(스프레드 급증, 체결률 급락)

검증 절차
	•	Walk‑forward: 앵커드 또는 expanding 6분할 (훈련→검증→OOS)
	•	어블레이션: z_c,z_d,z_r,\dots 제거 효과로 AUC/IC/PnL 변화
	•	버킷팅: h_t decile 별 사건율·PnL after‑cost 단조성 확인
	•	교차시장: 코인/거래소/시간대별 메타‑분석(랜덤효과 모델)
	•	현실성 검사: 주문빈도·참여율·슬리피지 분포가 실제와 근사?

리포트
	•	After‑cost CAGR, Sharpe, Sortino, Turnover·Participation, cost decomposition(스프레드/수수료/충격), hit ratio vs hazard decile

⸻

9) 파라미터 권장(시작점)

파라미터	제안	비고
\Delta	0.5s	점프 라벨 지평
\kappa	2.0σ	점프 임계
\gamma	2.0	비선형 증폭
\tau	hazard 0.7	게이팅 하한
\phi	1.0	비용 패널티
EWM HL	3s	표준화/평활
Winsor	1%	테일 억제
MaxPart	2–5%	참여율 상한
Kill‑switch	spread z > 3	거래 일시 중지


⸻

10) 실전 운영(모니터링 & 드리프트)
	•	모형 캘리브레이션: 주기적 리핏(일 1회/주 1회), calibration slope/Intercept 감시
	•	데이터 품질: 타임스탬프 드리프트, 주문·체결 누락률, 스냅샷 지연
	•	센터 리밸런스: 레짐 전환 감지(변동성/스프레드 체 regime) → 파라미터 테이블 전환
	•	SLO: 알파→오더→체결까지 p95 지연 목표치(예: < 30ms)

⸻

11) 의사코드(핵심 파이프라인)

# 1) 데이터 스트림에서 LOB/Trades 수집 → feature state 업데이트
state.update_from_lob(lob_snapshot)
state.update_from_trades(trade_batch)

# 2) 특징량 무차원화 & 평활
z = standardize_ewm(features=compute_features(state), hl=3.0, winsor=0.01)

# 3) Hazard & Direction
h = sigmoid(beta0 + beta1*softplus(z['cancel_int'])
                    + beta2*softplus(z['depth_cliff'])
                    + beta3*z['requote_delay']
                    + beta4*np.log1p(max(0, z['exec_pressure']))
                    + beta5*z['spread_state']
                    + beta6*abs(z['dOBI_dt']))

g = np.tanh(eta0 + eta1*z['ofi'] + eta2*z['micro_slope']
                 + eta3*np.sign(z['ofi_raw'])*z['exec_pressure'])

# 4) 비용/체결률
impact_hat = k_impact * sigma * np.sqrt(order_size / max(daily_vol, eps))
C = spread/2 + taker_fee + impact_hat
pi = fill_rate_ewm  # 최근 충족률

# 5) 알파 & 포지션
alpha = max(h**gamma - tau, 0.0) * g * pi * np.exp(-phi * C)
target_pos = k_risk * alpha
order = sizing_and_routing(target_pos, current_pos, lob_snapshot, limits)


⸻

12) 1초~1분 프록시 버전(캔들만 있을 때)
	•	OFI 프록시: tick rule로 매수/매도 플로우 근사
	•	스프레드 프록시: 고가-저가 대비 분모로 근사 스프레드 상태
	•	Depth proxy: 롤링 체결량/레인지로 유동성 대용량 지표
	•	Hazard: 위와 동일 구조(softplus/로그 포화), 단 레짐을 더 보수적으로

예시 특징(1m):
	•	z_e = z\big( \text{Vol}{1m} / \text{ATR}{5m} \big), z_s = z\big( \text{High-Low}/\text{Mid} \big)
	•	z_d = z\big( \text{Vol}{1m} / \text{Vol}{10m} \big) (유동성 급감 프록시)
	•	나머지 동일. 실행은 제한(Market only, 참여율↓).

⸻

13) 진단 & 안정화 체크리스트
	•	Information Coefficient(IC): Δ수익률과 \alpha_t 상관 (pre/post-cost)
	•	PSR/White’s Reality Check: 우연 성과 배제
	•	CSCV(Combinatorially Symmetric Cross‑Validation): 파라미터 튜닝 견고성
	•	Permutation test: 라벨 무작위화 시 성과 붕괴?
	•	Leakage test: 라벨 정의·표준화에서 미래정보 사용 여부 자동 검사

⸻

14) 실패 모드 & 가드레일
	•	유동성 공백: h_t↑와 동시에 스프레드 폭주 → 시장가 금지, 지정가 only
	•	피크 체결 폭주: 체결률 \pi_t 급락 시 알파=0로 게이팅
	•	연속 손실: per‑regime drawdown 한도 초과 시 해당 레짐 파라미터 freeze
	•	데이터 글리치: 스냅샷 중복/역타임스탬프 검출 → 그 구간 무거래

⸻

15) 확장 아이디어(암호화폐 특화)
	•	강제청산 히트맵: 폐포(Liquidation) 근접 클러스터를 z_e·z_o에 마크 → h_t 가중
	•	펀딩/베이시스 전이: 레짐 태깅에 추가(펀딩 급변 시 hazard threshold↑)
	•	마크드 Hawkes: (cancel, market buy, market sell, requote)를 마크로 → h_t 대체
	•	옵션 감마 피드백: 델타헤지 수요 추정량을 z_e에 가산

⸻

결론

이 설계는 (1) 사건 발생확률(hazard)로 선행성 확보 → (2) 방향 가이팅으로 한쪽 tail만 활용 → (3) 비용·체결률 내재화로 실전 PnL 정합을 달성합니다.
위 표준안을 그대로 구현하시면 거래소·자산·시간대가 달라도 재사용 가능한 비선형 알파 파이프라인이 됩니다.
