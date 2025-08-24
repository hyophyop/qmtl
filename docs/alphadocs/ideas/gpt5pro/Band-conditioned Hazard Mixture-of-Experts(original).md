아래는 지금까지 논의한 APB(허용밴드)·GATI/EDVH(갭·큐고갈 해저드)·EDCT(수축×강도×레질리언스) 계열 알파를 비판적으로 통합해 만든, 제가 보기에 가장 유망한 형상입니다. 목표는 조작·계절성·집행비용에 강하고, 롱/숏 파라미터 완전 분리와 실전 집행 가능성을 동시에 만족하는 것입니다.

⸻

0) 한 문장 요약

BH-MoE (Band-conditioned Hazard Mixture-of-Experts):
**(밴드 위치/오버슈트)**로 레짐을 정하고, **(수축·강도·레질리언스·깊이·갭)**로 **점프 해저드(확률×크기)**를 계량하여, 추세(돌파) 전문가와 역추세(재진입) 전문가를 게이트로 스위칭·혼합하는 구조.

⸻

1) 왜 이 조합이 ‘가장 유망’인가 — 비판적 근거
	•	APB 단독의 한계: 이동평균±표준편차는 Bollinger류와 동형이며 증분성이 약합니다. ⇒ 우리는 예측분포 분위수 밴드와 오버슈트로 레짐 한정에만 사용(알파의 본체는 LOB 신호).
	•	GATI/EDVH 단독의 한계: \max 연산·L2 의존·스푸핑 취약. ⇒ 가중 합 간극 + 큐 고갈 해저드 + 기대 점프 크기로 재정의하고, 체류시간(유령호가) 필터를 포함.
	•	EDC(수축) 단독의 한계: 수축은 징후일 뿐 충분조건 아님. ⇒ 수축(엔트로피/HHI/EMD) × 강도(이벤트-시간) × 레질리언스(리필/유출) × **경로 저항(유효깊이·갭)**의 곱 구조로 점프 해저드에 직접 연결.
	•	집행 현실성: 해저드 상승 구간은 스프레드 확대·슬리피지가 동반. ⇒ Spread 패널티·참여율 상한·히스테리시스·디바운스를 알파에 내재화.

⸻

2) 피처(무차원·강건) — 롱/숏 완전 분리 설계

가격/밴드
	•	중심 \mu_t: Huber-EWMA 또는 칼만(관측=mid)
	•	폭 \sigma_t: |resid| EWMA 또는 HAR-RV(고빈도면 microstructure-robust RV)
	•	예측 분위수 밴드: [Q_q(S_{t+1}|\mathcal F_t),Q_{1-q}(\cdot)]
	•	오버슈트 O_t=\frac{\max\{0,|S_t-\mu_t|-k\sigma_t\}}{\sigma_t}
	•	PBX =\frac{S_t-\mu_t}{k\sigma_t} (로그가격/틱 기준, z-score)

수축(군집) — EDC 개선
	•	C_{ent}, C_{hhi}, C_{emd} → C^{ex}=w_1 z(C_{ent})+w_2 z(C_{hhi})+w_3 z(C_{emd}) (ToD/RV/Spread 조건부 잔차)

강도(속도) — 미분 금지, 이벤트-시간
	•	이벤트 바(체결수/거래량/불균형)에서 EMA/상태공간/Hawkes로 \lambda^{buy},\lambda^{sell}
	•	총 강도 \lambda_{tot}, 순강도 \Delta\lambda, 경사 \widehat{\nabla}\lambda_{tot} (SG/상태공간 추정)

레질리언스(리필/유출)
	•	측면별 유입 \mu^{a/b}, 유출 \rho^{a/b} → 긴장도 T^{a/b}=\rho^{a/b}/(\mu^{a/b}+\epsilon)

경로 저항(깊이·갭)
	•	유효깊이 \tilde D^{a/b}{1:K} (체류시간 \tau{\min} 미만 제외, 재호가 페널티)
	•	깊이 쐐기 W=\frac{\tilde D^a-\tilde D^b}{\tilde D^a+\tilde D^b}
	•	갭 벡터 \Delta^{a/b}_k (틱)

방향/비용 보조
	•	OFI, microprice slope, SpreadZ, VolSurprise(시계내 계절성 보정)

**모든 입력은 무차원(z-score·로그·틱)**로 정규화. Long/Short는 별도 파라미터 세트.

⸻

3) 점프 해저드(확률×크기) — 알파의 ‘핵심 엔진’

상방(롱 게이트) 확률:
p^{\uparrow}=\sigma\!\big(\eta^L_0+\eta^L_1 C^{ex}+\eta^L_2 \widehat{\nabla}\lambda_{tot}+\eta^L_3(-\log \tilde D^a_{1:K})+\eta^L_4 T^a+\eta^L_5 OFI+\eta^L_6 SpreadZ+\eta^L_7\,\text{micro-slope}\big)
하방(숏 게이트)도 대칭적으로 \eta^S 사용.

기대 점프 크기(ask 측 예):
\mathbb{E}[J^\uparrow]=\Delta^a_1+\zeta\sum_{k=2}^{K}\Pr\{Q\ge \tilde D^a_{1:k-1}\}\,\Delta^a_k
여기서 Q는 최근 시장매수 주문 사이즈의 상위 분위수. (bid 측은 대칭)

EDVH/EDCT 통합 지수
EDH^{\uparrow}=p^{\uparrow}\cdot \mathbb{E}[J^\uparrow],\qquad
EDH^{\downarrow}=p^{\downarrow}\cdot \mathbb{E}[J^\downarrow]

GATI(점프 크기)×EDCH/EDVH(확률)의 결합체로 이해하면 됩니다.

⸻

4) Mixture-of-Experts 구조 — 밴드 조건 스위칭

(A) 추세 전문가(돌파 추종; Long/Short 분리)

\alpha^{\text{mom},L}= \beta^L_1\,\mathrm{softsign}(\beta^L_2\,(EDH^{\uparrow}))\cdot \exp(-\kappa^L\,SpreadZ)\cdot(1+\lambda^L\,VolSurprise)\cdot \mathbb{1}\{|PBX|>\theta^L_{band}\}
\alpha^{\text{mom},S}= -\beta^S_1\,\mathrm{softsign}(\beta^S_2\,(EDH^{\downarrow}))\cdot \exp(-\kappa^S\,SpreadZ)\cdot(1+\lambda^S\,VolSurprise)\cdot \mathbb{1}\{|PBX|>\theta^S_{band}\}

(B) 역추세 전문가(밴드 재진입·평균회귀)

\alpha^{\text{rev},L}= -\gamma^L_1\,\mathrm{softplus}\!\Big(\gamma^L_2\big(\theta^L_{in}-|PBX|\big)\Big)\cdot\mathbb{1}\{|PBX|<\theta^L_{out}\}\cdot \mathbb{1}\{EDH^{\uparrow/\downarrow}\ \text{낮음}\}
(숏도 대칭) — 히스테리시스 \theta_{in}>\theta_{out}로 채터링 방지.

(C) 최종 혼합(게이트)

w^{\text{mom}}=\sigma(\omega_0+\omega_1 O+\omega_2 C^{ex}+\omega_3 \widehat{\nabla}\lambda_{tot}),\quad
\alpha= w^{\text{mom}}(\alpha^{\text{mom},L}+\alpha^{\text{mom},S})+(1-w^{\text{mom}})(\alpha^{\text{rev},L}+\alpha^{\text{rev},S})

사이징(리스크 표준화)
w_{t}^{L/S}=\mathrm{clip}\!\left(w_{\max}^{L/S}\cdot\frac{|\alpha^{L/S}t|^{\phi^{L/S}}}{\widehat{\sigma}H},\ [-w{\max}^{S},w{\max}^{L}]\right)\cdot \mathrm{sign}(\alpha^{L/S}_t)

⸻

5) 1·2·3차 효과(인과 사슬) — 운영적 직관
	1.	1차: C^{ex}\uparrow & \widehat{\nabla}\lambda_{tot}\uparrow & T^{a/b}\uparrow & \tilde D^{a/b}\downarrow
	2.	2차: 최우선 큐 고갈→ 갭 통과→ 스프레드 확대(Re-quote 지연)
	3.	3차: 점프 실현 & 자기흥분 체결/취소→ IV 상승·군집 변동성

⸻

6) 실전 방어장치(필수)
	•	유령호가 차단: 체류시간 \tau_{\min} 미만 제외, 재호가 페널티.
	•	샘플링: 캘린더 시간 대신 이벤트 바(체결수/거래량/불균형).
	•	디바운스: CUSUM 또는 연속 N바 중 M바 만족 시만 발동.
	•	집행: Almgren–Chriss로 참여율 상한, 리밋/마켓 혼합, 개장·마감·공시 직후 금지구역.
	•	비용 내재화: SpreadZ 패널티와 참여율 제약을 알파에 곱해 신호-집행 동형성 확보.

⸻

7) 검증·통계(표준 절차; de facto)
	•	Purged K-fold + Embargo(누수 방지; Lopez de Prado)
	•	겹침수익 보정: Newey–West 또는 block bootstrap
	•	Deflated Sharpe / White’s Reality Check(다중가설)
	•	요인 중립화: 모멘텀/리버설/유동성/시총/가치 노출 제거 후 증분 알파만 평가
	•	TC/슬리피지 모델: 파워법칙 충격(Participation^\alpha) 포함
	•	앙커드 확장형 Walk-forward로 파라미터 업데이트

⸻

8) 실패 모드 & 극단 시나리오
	•	긍정적: 대규모 일방향 유입 + 얕은 경로 + 느린 리필 → EDH\!\uparrow → 추세 전문 알파 우수, 감마 스캘핑 병행 시 상승.
	•	중립: 수축은 강하지만 리필 빠름·강도 둔화 → 미실현(비용이 이익 상쇄).
	•	부정적(극단): 스푸핑/리밸런싱 착시로 C^{ex},\lambda 급등 → 체결 전 회수·역방향 급체결 + 스프레드 폭증 → 연속 손실.
대응: 체류시간·재호가 필터, 히스테리시스 임계, 금지구역, 참여율 상한, 킬스위치(SpreadZ·EDH 급변 시 위험 축소).

⸻

9) 데이터 등급별 구현 가이드
	•	L2 이상(권장): 위 설계 그대로.
	•	L1만 가능(현실적 대안):
	•	수축: 실행가격 히스토그램의 C_{ent}, C_{hhi}, EMD
	•	강도: 이벤트 바에서 거래수/대금 EMA
	•	경로 저항: “가격 점프당 체결량”으로 가상 누적깊이, 유효스프레드 복원 속도로 레질리언스 근사
	•	OFI 프록시·microprice 근사로 방향성 보정

⸻

10) 파라미터 표 (롱/숏 완전 분리)

모듈	Long	Short	비고
밴드 임계 \theta_{band}	\theta_{band}^L	\theta_{band}^S	레짐 경계
수축 가중 w	w^L	w^S	ent/hhi/emd
깊이 범위 K	K^L	K^S	1–5 레벨
게이트 \eta	\eta^L	\eta^S	로지스틱
포화 \beta	\beta^L	\beta^S	softsign 강도
히스테리시스 \theta_{in/out}	\theta^L_{in/out}	\theta^S_{in/out}	진입/해제 분리
Spread 패널티 \kappa	\kappa^L	\kappa^S	비용 내재화
사이징 \phi, w_{\max}	\phi^L,w^L_{\max}	\phi^S,w^S_{\max}	리스크 예산


⸻

11) 구현·배치 팁 (Qlib / PyTorch / freqtrade)
	•	Qlib: feature 노드(수축·강도·깊이·레질리언스·밴드) → model 노드(EDH·게이트·전문가) → portfolio/execution(Almgren–Chriss)
	•	PyTorch(MPS): Apple Silicon에서 device="mps"로 실시간 추론 가능.
	•	freqtrade(저빈도 파생): 프록시 피처로 구현하며 can_short=True 명시. 레짐 게이트·히스테리시스·참여율 한도를 그대로 이식.

⸻

12) “아이디어 자체가 글러먹었다면?”에 대한 대안
	•	본 조합은 속도 비대칭/수축만으로 알파를 내지 않고, 레질리언스 붕괴 + 경로 저항 + 갭을 곱 구조로 묶어 충분조건에 근접시키므로 폐기 필요 없음.
	•	그럼에도 데이터 품질(L2 미비)·집행 제약이 크다면, ARTT(Resiliency Threshold)—“리필<유출” 하한 돌파 + 얕은 경로 + 갭 존재 시에만 추세 전문가 가동—로 단순화한 보수형 변종을 권장.

⸻

결론

BH-MoE는
	•	**APB(밴드)**를 레짐 한정기로,
	•	EDC/AEVT의 수축·강도를 해저드 가중기로,
	•	GATI/EDVH의 깊이·갭·큐고갈을 점프 크기·확률 추정기로 통합한 집행가능 비선형 알파입니다.
조작·계절성·비용을 내재적으로 억제하고, 롱/숏 비대칭을 자연스럽게 품습니다. 원하시면 위 설계를 바로 돌릴 수 있는 Qlib 파이프라인/학습·검증 스크립트 또는 freqtrade 변형 골격을 제공하겠습니다.