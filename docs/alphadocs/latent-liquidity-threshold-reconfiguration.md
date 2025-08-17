📌 시장 미시 구조 이론: 잠재 유동성 임계 재구성 이론 (Latent Liquidity Threshold Reconfiguration Theory)

🏛 이론 개요

잠재 유동성 임계 재구성 이론은 주문서에 숨겨진 유동성이 특정 임계 수준에서 급격히 재배치되며, 이때 가격 충격이 비선형적으로 증폭된다고 설명합니다.

이 문서는 gpt5pro 모델이 재해석한 아이디어를 기반으로 구현되었으며, 세부 비평 및 확장 아이디어는 `docs/alphadocs/ideas/gpt5pro/latent-liquidity-threshold-reconfiguration.md`에서 확인할 수 있습니다.

⸻

📈 비선형 퀀트 알파 생성 방법
1. 잠재 유동성 임계치 추정
   LLR_t = \frac{Q_t}{\text{Depth}_t}
2. 임계 재구성 지표
   R_t = \frac{d}{dt} LLR_t
3. R_t 가 0 을 상향 돌파하면 유동성 공급 축소를 가정한 숏 포지션을, 하향 돌파하면 롱 포지션을 고려합니다.
