아래 “동적 체결 확산–수축(EDC)” 아이디어를 비판적으로 해체한 뒤, 이론적 결함과 실전 리스크를 보완하는 정교화 알파를 제안합니다. 아이디어 자체가 성립하기 어려운 경우의 대체 프레임도 함께 제시합니다. (롱/숏 파라미터는 전부 분리합니다.)

⸻

0) 한눈에 보기 (요약)
	•	조건부 유효성: “체결이 한정된 가격대에 군집(수축) + 공격적 유입 가속”이 **경로 저항(얕은 유효깊이·갭)**과 결합할 때 점프 해저드가 의미 있게 상승.
	•	핵심 결함
	1.	EDCI는 단위·정의 불일치(무차원화 미흡, \tau의 중복 사용), 노이즈가 심한 미분(d/dt) 의존.
	2.	**평균 깊이(MeanDepth)**가 비대칭 유동성을 숨김(ask와 bid의 경로 저항이 다름).
	3.	“수축”만으로는 충분조건 아님 — **리필(레질리언스)**와 취소/체결 유출을 동시에 봐야 함.
	4.	스푸핑/재호가(quote churn), 시계내 계절성(개장/마감), 동시성·타임스탬프 이슈에 취약.
	•	개선 방향:
	•	“수축”은 분포의 구조적 일탈로 측정(엔트로피·HHI·Wasserstein/EMD),
	•	“속도”는 **이벤트-시간 강도(EMA/Hawkes/상태공간)**로 추정(미분 제거),
	•	“전이”는 점프 확률×크기의 해저드 지수로 연결(게이팅·히스테리시스·포화 제어).

⸻

1) 원 제안(EDCI)의 유효성 vs. 이론적 결함

(1) 유효성(언제 먹히는가)
	•	1차 효과: 체결이 소수 가격빈에 몰리면(수축) 지역적 유동성이 빠르게 고갈되고, 작은 추가 유입에도 점프가 발생하기 쉬움.
	•	2차 효과: 마켓메이커는 재고·VaR 제한으로 스프레드 확장/리필 지연 → 점프 해저드 추가 상승.
	•	3차 효과: 초기 점프가 트리거가 되어 자기흥분 체결/취소가 연쇄(피드백) → 군집형 변동성과 IV 상승.

(2) 치명적 결함
	•	EDCI 단위/정의:
EDCI=\frac{\mathrm{Var}(P_{exec})}{\mathrm{MeanDepth}}\cdot\frac{d\,AggFlow}{dt}
	•	\mathrm{Var}(P)은 가격 단위, \mathrm{MeanDepth}는 수량 단위 → 무차원 아님.
	•	d/dt는 고주파 노이즈와 동기화 오차에 과민(브로커/거래소 지연 차).
	•	\tau를 창 길이와 임계치에 동시에 사용 → 모호성/과최적화 유도.
	•	MeanDepth의 맹점: 한쪽(ask/bid)만 얕아도 평균은 높게 보일 수 있어 경로 저항을 왜곡.
	•	스프레드 가속도 d^2Spread/dt^2: 실무에선 극도로 노이즈, 재호가/경매 이벤트에 의해 왜곡.
	•	내생성/조작 취약: 스푸핑으로 일시적 수축·유입 가속 연출 가능. 체류시간·재호가 고려가 없으면 허위 신호.

⸻

2) 실전 위험(데이터·집행·통계)
	•	데이터: 체결 서명(Lee–Ready) 오류, 거래소간 타임스탬프 비동기, 체류시간 미포착, 숨은 유동성(iceberg).
	•	집행: 신호 발생 구간은 대개 스프레드 확대·슬리피지↑. Almgren–Chriss급 스케줄링 없이 추종 시 거래비용이 알파를 압도.
	•	통계: 시계내 계절성(개장/마감), 공시·리밸런싱 이벤트 → 가짜 양(양의 선택 편향). Purged CV/Deflated SR 미적용 시 오버핏 확률↑.

⸻

3) 개선 프레임: EDCT — Execution Diffusion–Contraction Transition

(EDCI를 대체하는, 무차원·강건·집행가능한 지표)

3.1 수축(군집) 측정 — 분포 기반 무차원화

최근 N건 공격적 체결을 가격-틱 그리드 B개 빈으로 집계:
	•	정규화 엔트로피: H=-\sum p_i\log p_i, C_{ent}=1-H/\log B
	•	HHI: C_{hhi}=\sum p_i^2
	•	Wasserstein-1(EMD): 현재 분포 vs. 기준선 분포(동일 ToD, RV, spread 조건)의 이동거리 C_{emd}

통합 수축 점수(무차원)
C^{ex}t= w_1 z(C{ent}) + w_2 z(C_{hhi}) + w_3 z(C_{emd})
(모두 z-score; 로그가격/틱 단위 사용)

3.2 유입 “속도” — 이벤트-시간 강도(미분 제거)
	•	이벤트 바(체결수/거래량/불균형 바)에서 강도 \lambda^{buy/sell}를 EMA/상태공간/Hawkes로 추정.
	•	총 강도 \lambda_{tot}=\lambda^{buy}+\lambda^{sell}, 순 방향 강도 \Delta\lambda=\lambda^{buy}-\lambda^{sell}.
	•	속도 가속은 미분 대신 경사 추정(Savitzky–Golay/상태공간) 또는 \Delta\lambda의 이벤트-스텝 변화로 대체.

3.3 경로 저항 & 레질리언스
	•	유효깊이: 체류시간 \ge \tau_{\min} 조건의 누적 깊이 \tilde D^{a/b}_{1:K}.
	•	깊이 비대칭(경로 쐐기):
W=\frac{\tilde D^a_{1:K}-\tilde D^b_{1:K}}{\tilde D^a_{1:K}+\tilde D^b_{1:K}} \in [-1,1]
	•	레질리언스 긴장도(리필/유출 비):
T^{a}=\frac{\rho^{a}}{\mu^{a}+\epsilon},\quad T^{b}=\frac{\rho^{b}}{\mu^{b}+\epsilon}
(\rho: 체결+취소 유출, \mu: 신규 호가 유입)

3.4 점프 해저드(확률×크기)
	•	상방 해저드(롱 게이트):
p^{\uparrow}=\sigma\!\big(\eta^L_0+\eta^L_1 C^{ex}+\eta^L_2 \widehat{\nabla}\lambda_{tot}+\eta^L_3 (-\log \tilde D^a_{1:K})+\eta^L_4 T^a+\eta^L_5 OFI+\eta^L_6 SpreadZ\big)
	•	하방(숏 게이트)도 대칭적으로 \eta^S 계수.
	•	기대 점프 크기(ask 측 예):
\mathbb{E}[J^\uparrow]=\Delta^a_1+\zeta\sum_{k=2}^{K}\Pr\{Q\ge \tilde D^a_{1:k-1}\}\,\Delta^a_k
(Q: 최근 시장매수 주문 크기의 상위 분위수)
	•	EDCT 지수:
EDCT^{\uparrow}=p^{\uparrow}\cdot \mathbb{E}[J^\uparrow],\qquad
EDCT^{\downarrow}=p^{\downarrow}\cdot \mathbb{E}[J^\downarrow]

⸻

4) 최종 알파(히스테리시스·포화 제어·롱/숏 분리)

\begin{aligned}
g_t &= \exp(-\kappa^{L/S}\,SpreadZ)\cdot(1+\lambda^{L/S}\,VolSurprise) \\
\alpha^{L} &= \beta^L_1\,\mathrm{softsign}\!\big(\beta^L_2(EDCT^{\uparrow}-\theta^{L}{in})\big)\cdot\mathbb{1}\{EDCT^{\uparrow}>\theta^{L}{out}\}\cdot g_t \\
\alpha^{S} &= -\beta^S_1\,\mathrm{softsign}\!\big(\beta^S_2(EDCT^{\downarrow}-\theta^{S}{in})\big)\cdot\mathbb{1}\{EDCT^{\downarrow}>\theta^{S}{out}\}\cdot g_t \\
\alpha &= \alpha^{L}+\alpha^{S}
\end{aligned}
	•	히스테리시스: \theta_{in}>\theta_{out} (채터링 방지).
	•	포화 제어: \tanh 대신 softsign/softplus로 tail 민감도 유지.
	•	사이징(리스크 표준화):
w^{L/S}=\mathrm{clip}\!\left(w_{\max}^{L/S}\cdot\frac{|\alpha^{L/S}|^{\phi^{L/S}}}{\widehat{\sigma}H},\ [-w{\max}^{S},\,w_{\max}^{L}]\right)\cdot\mathrm{sign}(\alpha^{L/S})

⸻

5) 실전 방어장치 & 집행
	•	유령호가 필터: 체류시간 \tau_{\min} 미만 제외, 재호가 페널티(빠른 재등장 감점).
	•	샘플링: 캘린더 시간 대신 이벤트 바(체결수·거래량·불균형).
	•	디바운스: CUSUM/연속 N바 중 M바 충족 시 발동.
	•	집행: Almgren–Chriss로 참여율 상한, 리밋/마켓 혼합; 개장/마감/공시 직후 금지구역.

⸻

6) L1만 있을 때(LOB 부재) — 프록시 설계
	•	수축: 최근 N틱 실행가격 히스토그램의 C_{ent}, C_{hhi} + EMD(가격-틱)(기준선은 종가-중심/ToD matched).
	•	강도: 이벤트 바에서 거래수·거래대금으로 \lambda 추정(EMA/상태공간).
	•	경로 저항: “가격 점프당 체결량”으로 가상 누적깊이 근사; 유효스프레드의 복원 속도로 레질리언스 근사.
	•	방향성: OFI 프록시(체결 서명), 마이크로프라이스 기울기 근사.

⸻

7) 검증 프로토콜(필수)
	1.	라벨: “C^{ex}\uparrow & \widehat{\nabla}\lambda_{tot}\uparrow” 이벤트 후 수평선 h 내 점프(틱) 측정(이벤트 스터디).
	2.	교차검증: Purged K-fold + Embargo; 겹침수익은 Newey–West/블록 부트스트랩.
	3.	다중가설: Deflated Sharpe / White’s Reality Check.
	4.	요인 중립화: 모멘텀/리버설/유동성 회귀로 증분 알파만 측정.
	5.	거래비용: 파워법칙 충격 Impact\propto Participation^\alpha 포함; 슬리피지 상한.
	6.	레짐 이동: BOCPD/변화점 검정으로 파라미터 재평가 시점 자동화.

⸻

8) 롱/숏 파라미터(완전 분리; 예시 테이블)

모듈	Long	Short	메모
수축 윈도 N	N^L	N^S	이벤트 바 기준
깊이 범위 K	K^L	K^S	1–5 레벨
엔트로피/HHI/EMD 가중 w	w^L	w^S	합 1
게이트 \eta	\eta^L	\eta^S	로지스틱
히스테리시스 \theta_{in/out}	\theta_{in/out}^L	\theta_{in/out}^S	진입/해제 분리
포화 \beta	\beta^L	\beta^S	softsign 강도
감쇠 \kappa	\kappa^L	\kappa^S	Spread 패널티
사이징 \phi	\phi^L	\phi^S	리스크 예산


⸻

9) 코드 스켈레톤 (PyTorch/MPS; Qlib/집행 연결 용이)

Apple Silicon 가속: device="mps" 권장. 아래는 구조만 제시합니다.

import torch, torch.nn.functional as F

def contraction_scores(exec_ticks, exec_sizes, bins, baseline_hist):
    # 현재 분포
    hist = torch.histc(exec_ticks, bins=bins,
                       min=exec_ticks.min(), max=exec_ticks.max(),
                       weights=exec_sizes)
    p = hist / (hist.sum() + 1e-12)
    # 엔트로피/HHI
    H = -(p.clamp_min(1e-12) * p.clamp_min(1e-12).log()).sum()
    C_ent = 1.0 - H / (torch.log(torch.tensor(float(bins))))
    C_hhi = (p**2).sum()
    # 간단 EMD 근사(누적분포 거리)
    cdf = torch.cumsum(p, 0)
    cdf0 = torch.cumsum(baseline_hist / (baseline_hist.sum() + 1e-12), 0)
    C_emd = (cdf - cdf0).abs().sum()
    return C_ent, C_hhi, C_emd

def intensity_ema(x, alpha=0.2):
    y = torch.zeros_like(x); y[0] = x[0]
    for t in range(1, len(x)):
        y[t] = alpha * x[t] + (1 - alpha) * y[t-1]
    return y

def gate_prob(features, eta):  # features: [...,] normalized
    return torch.sigmoid(eta[0] + (eta[1:] * features).sum(-1))

def expected_jump(gaps_ticks, cum_depth, Qq, zeta=0.5):
    pj = (cum_depth <= Qq).float() + 0.5*(cum_depth > Qq).float()
    return gaps_ticks[0] + zeta * (pj[1:] * gaps_ticks[1:]).sum()

def alpha_side(EDCT, beta, spread_z, vol_surp, kappa, lam, theta_in, theta_out, sign):
    core = beta[0] * F.softsign(beta[1] * (EDCT - theta_in))
    gate = (EDCT > theta_out).float()
    g = torch.exp(-kappa * spread_z) * (1 + lam * vol_surp)
    return sign * core * gate * g

	•	Qlib: feature 노드(수축·강도·깊이·레질리언스) → model 노드(게이트/알파) → portfolio/execution(Almgren–Chriss, 참여율 상한).
	•	freqtrade 저빈도 파생 시 can_short=True 필수 포함.

⸻

10) 극단 시나리오(요청 성향 반영)
	•	긍정적: 수축 C^{ex}\uparrow + 총 강도 가속 \widehat{\nabla}\lambda_{tot}\uparrow + 얕은 경로(\tilde D\downarrow)
→ 1차 큐 고갈 위험↑ → 2차 점프 발생 & 스프레드 확장 → 3차 자기흥분 연쇄·IV 상승.
	•	중립: 수축 강하나 리필 빠름(T\downarrow) → 점프 미실현, 비용이 이익 상쇄.
	•	부정적(극단): 스푸핑/리밸런싱 착시로 C^{ex}·강도 급등 → 체결 전 회수·역방향 급체결 + 스프레드 폭증 → 연속 손실.
대응: 체류시간 필터·재호가 페널티·히스테리시스·금지구역·참여율 상한.

⸻

11) “아이디어 자체가 글러먹었는가?” — 대체 제안(비판 유지)

대체 프레임: ARTT — Asymmetric Resiliency Threshold Trading
	•	주장: 전이는 “속도”보다 레질리언스 붕괴(리필 < 유출)가 직접 원인.
	•	지표: R^{side}=\mu^{side}-\rho^{side} 가 하한 돌파 & 얕은 경로 & 갭 존재일 때만 게이트 개방.
	•	장점: 일시적 유입(스푸핑)에 강함. 진짜 리필 부진이 포착될 때만 작동.
	•	한계: L2/L3 품질·거래소별 구조 차이 보정 필요(현실적 제약).

⸻

12) 체크리스트(실전 도입 전)
	•	로그/틱 기반 무차원 수축 점수(엔트로피·HHI·EMD)
	•	이벤트-시간 강도(EMA/Hawkes)로 가속 추정(미분 제거)
	•	경로 저항(유효깊이·갭) & 레질리언스(리필/유출) 포함
	•	EDCT = 확률×크기 + 히스테리시스 + softsign
	•	유령호가/재호가 방어 + CUSUM 디바운스
	•	Purged CV / Newey–West / Deflated SR / 요인 중립화
	•	Almgren–Chriss 집행, 참여율·슬리피지 상한, 금지구역

⸻

맺음말

“체결의 수축”은 전이의 징후일 뿐 충분조건이 아닙니다. **(수축의 비정상성) × (유입 가속) × (경로 저항/레질리언스 붕괴)**를 곱 구조로 모델링한 EDCT는 단위 일관성과 조작 내성을 확보하면서 집행 가능한 비선형 알파로 연결됩니다.
원하시면 위 프레임을 Qlib 파이프라인 또는 freqtrade(can_short=True) 전략 골격으로 바로 옮겨 드리겠습니다.