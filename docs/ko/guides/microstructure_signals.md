# 마이크로스트럭처 신호: 탑-오브-북 불균형과 미크로-프라이스

짧은 체결 주기에서 유동성 편향을 관측하려면 **탑-오브-북 불균형(top-of-book
imbalance)**과 **미크로-프라이스(micro-price)** 조합이 가장 먼저 떠오릅니다. 이
문서는 QMTL 런타임에 새로 추가된 노드들을 활용해 해당 신호를 계산하고, 노이즈에
강한 로지스틱 가중치를 적용하는 방법을 정리합니다.

## 탑-오브-북 불균형 노드

`order_book_imbalance_node`는 최우선 매수/매도 잔량을 받아

\[
I = \frac{Q_{\text{bid}} - Q_{\text{ask}}}{Q_{\text{bid}} + Q_{\text{ask}}}
\]

공식을 그대로 계산해 -1부터 +1 사이의 균형 지표를 반환합니다. 값이 +1에 가까울수록
매수 잔량 우위, -1이면 매도 잔량 우위를 의미합니다.

## 로지스틱 가중치 노드

실제 호가창에서는 잔량이 순간적으로 출렁이며 선형 지표가 과도하게 반응하는 경우가
잦습니다. `logistic_order_book_imbalance_node`는 균형값을 시그모이드 함수로 매핑해
가중치 `w ∈ [0, 1]`를 생성합니다.

- `slope`: 포화 속도를 제어하는 기울기입니다. 값이 크면 0 근처에서도 빠르게 0 또는 1로
  수렴합니다.
- `clamp`: 균형값을 절댓값 기준으로 잘라 얇은 호가에서 발생하는 극단값을 완화합니다.
- `offset`: 필요 시 균형값의 중심을 이동시켜 특정 구간을 더 민감하게 만들 수 있습니다.

## 미크로-프라이스 노드

`micro_price_node`는 최우선 호가(`best_bid`, `best_ask`)와 가중치 노드를 조합해

\[
P_{\text{micro}} = w\,P_{\text{ask}} + (1 - w)\,P_{\text{bid}}
\]

을 계산합니다. 이미 계산된 가중치를 입력하거나, 불균형 노드를 전달하고 `mode`를
`"linear"` 혹은 `"logistic"`으로 지정해 자동으로 가중치를 생성할 수 있습니다.

## 예제 코드

```python
from qmtl.runtime.sdk.node import SourceNode
from qmtl.runtime.transforms import (
    order_book_imbalance_node,
    logistic_order_book_imbalance_node,
    micro_price_node,
)

bid_volume = SourceNode(interval="1s", period=1, config={"id": "bid_volume"})
ask_volume = SourceNode(interval="1s", period=1, config={"id": "ask_volume"})
best_bid = SourceNode(interval="1s", period=1, config={"id": "best_bid"})
best_ask = SourceNode(interval="1s", period=1, config={"id": "best_ask"})

imbalance = order_book_imbalance_node(bid_volume, ask_volume)
logistic_weight = logistic_order_book_imbalance_node(
    bid_volume,
    ask_volume,
    slope=4.0,
    clamp=0.8,
)
micro_price = micro_price_node(best_bid, best_ask, weight_node=logistic_weight)
```

## 튜닝 가이드

- **slope** 값은 2~6 범위에서 시작해, 예측력이 가장 높은 값을 백테스트로 고르는 것이
  일반적입니다.
- **clamp**는 ±0.7~0.9 사이를 권장합니다. 너무 낮으면 정보 손실이, 너무 높으면 노이즈에
  다시 민감해집니다.
- `mode="linear"`는 잔량 비율을 그대로 활용하고 싶을 때 사용하세요. 로지스틱 모드가 기본
  값이며, 빠르게 포화되는 암호화폐/고빈도 시장에서 특히 효과적입니다.
- 가중치를 다른 알파와 결합할 때는 `imbalance_to_weight()` 헬퍼를 이용하면 동일한 로직을
  재사용할 수 있습니다.
