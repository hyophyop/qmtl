아래 “동적 체결 확산-수축(Execution Diffusion–Contraction)” 알파를 비판적으로 해체한 뒤, 집행 현실·마이크로구조·통계적 정당성을 반영한 **정교화 알파(롱/숏 분리)**를 제안합니다. 핵심은 *“분산(확산) vs. 군집(수축)”*을 가격축의 공간 통계 + 큐(대기물량) 역학 + 유입 체결 플럭스로 일관되게 계량화하고, **점프 위험(확률×크기)**으로 직접 연결하는 것입니다.

⸻

TL;DR — 문제 요약과 처방
	1.	정의/단위 문제:
\displaystyle EDCI_t=\frac{\mathrm{Var}(P_{\text{exec},t-\tau:t})}{\mathrm{MeanDepth}_t}\cdot\frac{d\,\text{AggFlow}_t}{dt} 는
	•	단위가 (\text{가격}/\text{시간})^2로 차원 비일관(시그모이드 입력은 무차원이어야 함).
	•	\tau 기호가 윈도 길이와 임계치에 동시에 사용되어 혼동.
	•	**가격 분산↓(수축)**이면 지표값이 작아지는데, 여기에 **체결 가속도(d/dt)**를 곱해 부호·스케일이 불안정.
	2.	신호의 내생성/누락 변수:
	•	“수축”만으로 점프는 충분조건이 아님. 큐 고갈 위험(취소·체결 유출 vs. 추가 유입), 경로상의 유효깊이, 갭 구조가 함께 작동해야 점프가 발생.
	•	평균깊이(MeanDepth)는 편향: 비대칭 유동성(한쪽만 얕음)을 숨김.
	3.	노이즈/마켓 메이킹 현실:
	•	개장·마감·리밸런싱의 시계내 계절성과 **재호가(quote churn)**가 분산·유량 추정치를 왜곡.
	•	극대화/미분 연산은 조작·스푸핑·초단기 이벤트에 과민.
	4.	알파 구조:
	•	단일 시그모이드는 포화·과민 문제. 게이팅 + (점프 확률)×(점프 크기) 구조가 집행·리스크 관점에서 더 적합.

⸻

1) “확산–수축”의 강건 계량: 공간통계 기반 대체 지표

1.1 실행가격의 공간(가격축) 농도를 직접 측정

최근 N건의 공격적 체결(marketable) 가격을 틱 그리드에 빈(bin)으로 집계:
	•	정규화 엔트로피(무차원):
H_t=-\sum_{i}p_{i,t}\log p_{i,t},\quad C^{(\text{ent})}t = 1-\frac{H_t}{\log B}
p{i,t}: 가격빈 i의 체결량 비중, B: 사용 빈 수.
\Rightarrow C^{(\text{ent})}\uparrow일수록 수축(군집) 강함.
	•	HHI/Gini 기반 농도(무차원):
C^{(\text{hhi})}t = \sum_i p{i,t}^2
엔트로피와 상보적으로 해석.
	•	근접도(Nearest-Neighbor): 연속 체결들의 틱 거리 \delta_j=|p_{j}-p_{j-1}|에 대해 Fano ratio
C^{(\text{fano})}_t=\frac{\mathrm{Var}(\delta)}{\mathbb{E}[\delta]}
가 낮을수록 군집.

세 지표를 z-score 표준화 후 결합해 C_t로 사용:
C_t=w_1 z(C^{(\text{ent})})+w_2 z(C^{(\text{hhi})})-w_3 z(C^{(\text{fano})})
(로그가격/틱 단위로 계산, 시계내 계절성 제거.)

1.2 “확산 속도”의 기준선 제거(Null 대비 초과 수축)
	•	기준선: 동일 구간의 **실현 변동성(HAR-RV 등)**과 스프레드로 예측한 기대 확산 분포.
	•	초과 수축: C_t^{\text{ex}} = C_t - \widehat{\mathbb{E}}[C|\text{RV},\text{Spread},\text{ToD}].
→ 마켓 상태가 만든 당연한 군집과 비정상 군집을 구분.

⸻

2) “압력(유입)”과 “방향(경로)”의 강건 추정

2.1 플럭스/가속도를 미분 대신 상태공간 필터로
	•	공격적 체결 순유입 F_t: (매수 market 체결량 − 매도 market 체결량).
	•	가속도 대체: 칼만/SG 필터로 추정한 \dot F_t(EWM 회귀 경사), 또는 \Delta F_t를 이벤트 바(체결수/거래량/불균형 바) 스텝으로 계산.
→ 미분 노이즈·지연 균형.

2.2 경로상의 유효깊이(path-of-least-resistance depth)
	•	상방(롱 시나리오): 미드~K레벨 ask 누적 유효깊이 \tilde D^a_{1:K} (체류시간 필터 포함).
	•	하방(숏): \tilde D^b_{1:K}.
	•	Depth wedge: W_t=\frac{ \tilde D^a_{1:K}-\tilde D^b_{1:K}}{ \tilde D^a_{1:K}+\tilde D^b_{1:K}} (−1…1).
→ 경로 비대칭성 반영(평균깊이의 맹점 보완).

2.3 OFI/마이크로프라이스 기울기 보강

OFI_t=\Delta D^b_1-\Delta D^a_1 + \text{(체결·취소 조정)},\quad
\Delta \text{MicroPx}_t = \text{microprice slope}
→ 방향 게이팅 변수.

⸻

3) “점프 위험 = 확률 × 크기”로 직결되는 개선 지수(EDCH)

3.1 고갈 해저드 기반 점프 확률

p^{\uparrow}_t=\sigma\!\Big(\eta_0+\eta_1 C^{\text{ex}}t+\eta_2 \dot F_t+\eta_3(-\log \tilde D^a{1:K})+\eta_4 OFI_t+\eta_5 \text{SpreadZ}_t+\eta_6 \Delta \text{MicroPx}_t\Big)
p^{\downarrow}_t=\sigma\!\Big(\tilde\eta_0+\tilde\eta_1 C^{\text{ex}}t+\tilde\eta_2 (-\dot F_t)+\tilde\eta_3(-\log \tilde D^b{1:K})+\tilde\eta_4 (-OFI_t)+\tilde\eta_5 \text{SpreadZ}_t-\tilde\eta_6 \Delta \text{MicroPx}_t\Big)
	•	무차원 입력(z-score/로그)로 정규화.
	•	롱/숏 완전 분리 파라미터(\eta \neq \tilde\eta).

3.2 기대 점프 크기
	•	인접 갭 기반(ask 측 상방 예):
\mathbb{E}[J^\uparrow_t]\approx \Delta^a_1+\zeta \sum_{k=2}^{K}\Pr\{Q\ge \tilde D^a_{1:k-1}\}\ \Delta^a_k
Q: 최근 시장매수 주문 크기의 분위수(75–90p). \Delta^a_k: k레벨 갭(틱).

3.3 EDCH(Execution Diffusion–Contraction Hazard) 지수

\boxed{\ EDCH^{\uparrow}_t= p^{\uparrow}_t\cdot \mathbb{E}[J^\uparrow_t],\qquad
EDCH^{\downarrow}_t= p^{\downarrow}_t\cdot \mathbb{E}[J^\downarrow_t]\ }
→ 방향 알파의 원석은 EDCH^{\uparrow}-EDCH^{\downarrow}.

⸻

4) 개선된 비선형 알파 (게이팅·포화 제어·롱/숏 분리)

\begin{aligned}
\alpha^{L}_t &= \beta^{L}_1\,\mathrm{softsign}\!\big(\beta^{L}_2 EDCH^{\uparrow}_t\big)\cdot g^{L}_t,\\
\alpha^{S}_t &= -\beta^{S}_1\,\mathrm{softsign}\!\big(\beta^{S}_2 EDCH^{\downarrow}_t\big)\cdot g^{S}_t,\\
\alpha_t &= \alpha^{L}_t+\alpha^{S}_t,
\end{aligned}
	•	g^{L/S}_t=\exp(-\kappa^{L/S}\,\text{SpreadZ}_t)\cdot (1+\lambda^{L/S}\,\text{VolSurprise}_t).
	•	softsign/softplus로 tail 포화 억제(\tanh보다 미분 정보 보존).
	•	사이징:
w^{L/S}t=\mathrm{clip}\!\left(w{\max}^{L/S}\cdot\frac{|\alpha^{L/S}t|^{\phi^{L/S}}}{\widehat{\sigma}H},\ [-w{\max}^{S},w{\max}^{L}] \right)\cdot \mathrm{sign}(\alpha^{L/S}_t)

⸻

5) 스푸핑/유령호가 방어 및 샘플링
	•	체류시간 필터: \tau_{\min} 미만 호가 제외 → 유효깊이 산출.
	•	재호가 페널티: 동일 레벨의 급속 재등장 감점.
	•	이벤트 바(체결수/거래량/불균형)로 정보등시화.
	•	디바운스: CUSUM 또는 “연속 N바 중 M바” 조건 충족 시 발동.

⸻

6) 검증·통계(오버핏 방지 필수)
	1.	라벨: “수축 강함 + 고갈 해저드↑” 이벤트 후 h 내 점프(틱) 측정.
	2.	Purged K-fold + Embargo로 누수 제거.
	3.	겹침수익 보정: Newey–West/블록부트스트랩.
	4.	다중가설: Deflated Sharpe / White’s RC.
	5.	요인 노출 제거: 모멘텀/리버설/유동성 회귀로 증분 알파만 평가.
	6.	거래비용: 파워법칙 충격 Impact\propto Participation^\alpha 포함.

⸻

7) 옵션/감마와의 접속
	•	EDCH^{\uparrow/\downarrow}\uparrow & IV 상승 동조 시 감마 스캘핑/스트래들 우위.
	•	수축→해저드 급등 구간은 델타 리헤지 빈도↑, 재확산·재호가 회복 시 완화.
	•	IV–HV 필터로 변동성 포지션 방향 결정.

⸻

8) 롱/숏 파라미터 제안(완전 분리)

모듈	Long	Short	비고
N(체결수 창)	N^L	N^S	이벤트 바 기준
K(깊이 범위)	K^L	K^S	1–5레벨 권장
농도 가중 w	w^L	w^S	ent/hhi/fano 비율
해저드 계수 \eta	\eta^L	\eta^S	로지스틱
포화 \beta	\beta^L	\beta^S	softsign 강도
감쇠 \kappa	\kappa^L	\kappa^S	스프레드 패널티
사이징 \phi	\phi^L	\phi^S	리스크 예산


⸻

9) 구현 스켈레톤 (PyTorch/MPS; Qlib/집행 연결 용이)

import torch

def concentration_scores(exec_prices_ticks, exec_sizes, bins, tod_features):
    # 히스토그램 분포
    hist = torch.histc(exec_prices_ticks, bins=bins, min=exec_prices_ticks.min(), max=exec_prices_ticks.max(), weights=exec_sizes)
    p = hist / (hist.sum() + 1e-12)
    # 엔트로피/HHI/Fano
    entropy = -(p * (p.clamp_min(1e-12)).log()).sum()
    hhi = (p**2).sum()
    # 연속 체결 간 틱거리
    d = (exec_prices_ticks[1:] - exec_prices_ticks[:-1]).abs()
    fano = d.var(unbiased=False) / (d.mean() + 1e-12)
    # z-score는 외부에서 시계내 계절성·스프레드 등으로 정규화
    return entropy, hhi, fano

def hazard_prob(C_ex, F_dot, log_inv_depth, ofi, spread_z, micro_slope, eta):
    x = torch.stack([C_ex, F_dot, log_inv_depth, ofi, spread_z, micro_slope])
    return torch.sigmoid(eta[0] + (eta[1:] * x).sum())

def expected_jump(gaps_ticks, cum_depth, Q_quantile, zeta=0.5):
    # 1레벨 점프 + 연쇄 고갈 기대
    pj = (cum_depth <= Q_quantile).float() + 0.5*(cum_depth > Q_quantile).float()
    return gaps_ticks[0] + zeta * (pj[1:] * gaps_ticks[1:]).sum()

def alpha_side(EDCH, beta, spread_z, vol_surp, kappa, lam, sign):
    core = torch.nn.functional.softsign(beta[1] * EDCH) * beta[0]
    g = torch.exp(-kappa * spread_z) * (1 + lam * vol_surp)
    return sign * core * g

	•	Apple Silicon: torch.device("mps") 사용.
	•	Qlib: feature(농도·해저드·갭) → model(게이트/사이징) → portfolio/execution(Almgren–Chriss/참여율 상한)로 연결.
	•	freqtrade 파생 시 can_short=True 포함.

⸻

10) 극단 시나리오 (요청 성향 반영)
	•	긍정적: 대규모 동일방향 시장주문 유입 → 수축C^{ex}\uparrow + 얕은 경로(\tilde D\downarrow) + 갭 존재 → p\!\uparrow, \mathbb{E}[J]\!\uparrow ⇒ 추세 동승 + 감마 스캘핑 수익.
	•	중립: 수축은 강하나 재호가 빠르고 플럭스 약함 → p 낮아 미실현(비용이 이익 상쇄).
	•	부정적(극단): 스푸핑·리밸런싱 착시로 C 급등, 실행 전 회수 → 역방향 체결 급증·스프레드 확대 ⇒ 연속 손실.
대응: 체류시간 필터·재호가 페널티·이벤트바 디바운스·금지구역(개장/마감/공시 직후) 적용.

⸻

11) 관련 분야(지식 확장)
	•	포인트 프로세스/호크스(Hawkes): 수축은 자기흥분(브랜칭 비율) 증가와 상통 → C^{ex}를 내생성 지표로 해석.
	•	공간통계(Entropy/HHI/Ripley K): 가격축 상 군집성 측정의 표준 틀.
	•	신경과학: 발화 군집–발화 빈도 가속 → 해저드 모델로 점프 확률 추정 정당화.
	•	신호처리: Savitzky–Golay/상태공간 미분으로 노이즈 민감도 관리.

⸻

12) 실전 체크리스트
	•	로그/틱 기반 무차원 농도 C_t 산출(엔트로피·HHI·Fano 결합, 계절성 보정)
	•	유효깊이 \tilde D(체류시간·재호가 페널티)와 갭 계산
	•	OFI/마이크로프라이스 경사/SpreadZ/VolSurprise 포함
	•	EDCH = 확률×크기 구조로 재정의(롱/숏 분리)
	•	이벤트바 + CUSUM 디바운스
	•	Purged CV + NW/Deflated SR + 요인 중립화
	•	Almgren–Chriss 집행, 참여율 상한/슬리피지 상한

⸻

결론

“체결 분포의 수축” 자체는 징후에 불과합니다. **(비정상 군집)×(체결 유입 가속)×(경로상 낮은 유효깊이/갭)**이 결합할 때 점프 해저드가 의미 있게 상승합니다. 제안한 EDCH 프레임은 이 곱 구조를 무차원·강건하게 구현하여, 조작·계절성에 강하고 집행가능성이 높은 비선형 알파로 연결합니다.