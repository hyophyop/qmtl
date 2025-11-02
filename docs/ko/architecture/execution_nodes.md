---
title: "실행 레이어 노드"
tags: [architecture, execution, nodes]
author: "QMTL Team"
last_modified: 2025-08-21
---

# 실행 레이어 노드

프리트레이드 점검, 주문 사이징, 실행, 체결 수집, 포트폴리오 업데이트, 리스크 제어, 타이밍 게이트 등을 담당하는 래퍼 노드 집합입니다. 이 클래스들은 전략 신호를 [exchange_node_sets.md](exchange_node_sets.md)에 설명된 거래소 노드 세트와 연결하며 `qmtl/runtime/sdk` 하위 모듈을 활용합니다.

사용 메모
- 일반적인 전략에서는 이러한 노드를 하나씩 연결하기보다는 사전 구축된 노드 세트(래퍼)를 붙이는 것이 좋습니다. 노드 세트 API는 내부 구성 변화와 무관하게 안정적인 인터페이스를 제공합니다.

## 팬인(Fan-in) 패턴

노드는 둘 이상의 업스트림을 구독할 수 있어, 다운스트림 노드가 여러 입력(예: 가격 스트림과 지표 윈도)을 동시에 읽어 결합된 결정을 내리는 \"팬인\" 패턴을 구현합니다.

```mermaid
graph LR
    price[price stream] --> alpha[alpha]
    alpha --> hist[alpha_history]
    price --> combine
    hist --> combine[combine (fan-in)]
    combine --> signal[trade_signal]
    signal --> orders[publish_orders]
    orders --> router[router]
    router --> micro[MicroBatch]
```

예시 코드(CacheView 인덱싱은 업스트림 노드와 해당 인터벌을 사용합니다):

```python
from qmtl.runtime.sdk import Node, StreamInput
from qmtl.runtime.transforms import alpha_history_node, TradeSignalGeneratorNode
from qmtl.runtime.pipeline.execution_nodes import RouterNode
from qmtl.runtime.pipeline.micro_batch import MicroBatchNode

price = StreamInput(interval="60s", period=2)

def compute_alpha(view):
    data = view[price][price.interval]
    if len(data) < 2:
        return 0.0
    prev, last = data[-2][1]["close"], data[-1][1]["close"]
    return (last - prev) / prev

alpha = Node(input=price, compute_fn=compute_alpha, name="alpha")
history = alpha_history_node(alpha, window=30)

def alpha_with_trend_gate(view):
    hist_data = view[history][history.interval]
    price_data = view[price][price.interval]
    if not hist_data or not price_data:
        return None
    hist_series = hist_data[-1][1]  # list[float]
    closes = [row[1]["close"] for row in price_data]
    if len(closes) < 2:
        return hist_series
    # 가격 모멘텀이 하락할 때 양의 알파를 차단
    trend_up = closes[-1] >= closes[-2]
    return hist_series if trend_up else [v if v <= 0.0 else 0.0 for v in hist_series]

combined = Node(
    input=[history, price],  # 다중 업스트림(fan-in)
    compute_fn=alpha_with_trend_gate,
    name="alpha_with_trend_gate",
    interval=history.interval,
    period=history.period,
)

signal = TradeSignalGeneratorNode(combined, long_threshold=0.0, short_threshold=0.0)
orders = TradeOrderPublisherNode(signal)
router = RouterNode(orders, route_fn=lambda o: "binance" if str(o.get("symbol","")) .upper().endswith("USDT") else "ibkr")
micro = MicroBatchNode(router)
```

참고 사항
- `Node(input=[...])`: 업스트림 노드 이터러블을 전달해 팬인 노드를 생성합니다.
- `view[upstream][upstream.interval]`: `compute_fn` 내에서 각 업스트림의 최신 윈도에 접근합니다.
- 이벤트 시간 게이팅은 가장 느린 업스트림 워터마크를 사용하며, 지연 데이터 처리는 노드의 `allowed_lateness`/`on_late` 정책을 따릅니다.
