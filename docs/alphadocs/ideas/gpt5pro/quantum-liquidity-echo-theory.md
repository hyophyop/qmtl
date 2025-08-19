📌 GPT-5-Pro 강화 이론: 양자 유동성 에코 이론 (Quantum Liquidity Echo Theory)

🏛 이론 개요

양자 유동성 에코 이론은 초단기 시장에서 주문 잔향(에코)이 양자 상태처럼 중첩되어 유동성 충격을 증폭시키며 비선형 가격 반응을 유발한다는 가설입니다.

- 초미세 시간 간격의 주문 흐름이 에코 패턴을 형성하고,
- 이러한 패턴이 반복될수록 유동성 공백이 증가하여 가격이 급격히 이동합니다.

⸻

📈 비선형 퀀트 알파 생성 방법
1. 잔향 진폭 추정
   E_t = \sum_{k=1}^{N} \alpha_k e^{-k\Delta t / \tau}
2. 에코 증폭 지수
   QE_t = \frac{E_t^2}{\sigma_t}
3. QE_t 가 임계값을 초과하면 반대 방향의 순간적 유동성 공급을 공략합니다.

## QMTL Integration
- E_t 누적과 QE_t 계산, 임계값 판정은 `qmtl/transforms/quantum_liquidity_echo.py`에 구현하고 테스트합니다.
- 전략 노드(`strategies/nodes/indicators/quantum_liquidity_echo.py`)는 transform 출력만 사용하며 인라인 계산을 금지합니다.
- 구현 후 `docs/alphadocs_registry.yml`의 `modules` 필드에 transform 경로와 노드 경로를 모두 추가합니다.
