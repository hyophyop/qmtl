# RouterNode, MicroBatchNode, 테스트 키트 활용

이 짧은 가이드는 주문을 대상별로 라우팅하고, 페이로드를 마이크로배치하며, 테스트에서 Node Set을 빠르게 연결하는 방법을 소개합니다.

## RouterNode

각 주문에서 `route` 키(예: 거래소)를 계산해 라우팅합니다. 다운스트림 커넥터는 `order["route"]` 값을 기준으로 분기합니다.

```python
from qmtl.runtime.pipeline.execution_nodes import RouterNode

def route_fn(order: dict) -> str:
    sym = order.get("symbol", "")
    return "binance" if str(sym).upper().endswith("USDT") else "ibkr"

routed = RouterNode(orders, route_fn=route_fn)
```

## MicroBatchNode

최신 버킷의 페이로드 목록을 방출해 항목당 오버헤드를 줄입니다. 새 타임스탬프가 도착하면 직전 버킷을 플러시합니다.

```python
from qmtl.runtime.pipeline.micro_batch import MicroBatchNode

batches = MicroBatchNode(routed)
# 예: [{"symbol": "BTCUSDT", ...}, {"symbol": "ETHUSDT", ...}]
```

상세 설계와 배치 위치는 [아키텍처 → 거래소 Node Set](../architecture/exchange_node_sets.md) 문서를 참고하세요.

## Node Set 테스트 키트

테스트에서 시그널 뒤에 Node Set을 붙이고 웹훅 시뮬레이션용 가짜 체결 이벤트를 생성합니다.

```python
from qmtl.runtime.nodesets.base import NodeSetBuilder
from qmtl.runtime.nodesets.testkit import attach_minimal, fake_fill_webhook

ns = attach_minimal(NodeSetBuilder(), signal, world_id="demo")
evt = fake_fill_webhook("AAPL", 1.0, 10.0)
assert evt["type"] == "trade.fill" and evt["data"]["symbol"] == "AAPL"
```

전체 파이프라인 예시는 `qmtl/examples/strategies/order_pipeline_strategy.py` 를 참고하세요.
