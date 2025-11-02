# Node Set 테스트 키트

테스트에서 시그널 뒤에 Node Set을 빠르게 구성하고 페이크 웹훅 페이로드로 체결을 시뮬레이션하는 레시피를 소개합니다. 설계 배경은 [거래소 Node Set](../architecture/exchange_node_sets.md) 문서를 참고하세요.

## 테스트에서 최소 Node Set 연결

```python
from qmtl.runtime.sdk.node import Node
from qmtl.runtime.nodesets.base import NodeSetBuilder
from qmtl.runtime.nodesets.testkit import attach_minimal


def test_nodeset_attach_minimal():
    sig = Node(name="sig", interval=1, period=1)
    ns = attach_minimal(NodeSetBuilder(), sig, world_id="w1")
    order = {"symbol": "AAPL", "price": 10.0, "quantity": 1.0}
    # 스캐폴드의 각 스텁은 페이로드를 그대로 전달합니다.
    first = ns.head
    assert first is not None and len(list(ns)) == 7
```

## 페이크 체결 웹훅 이벤트 생성

```python
from qmtl.runtime.nodesets.testkit import fake_fill_webhook


def test_fake_fill_webhook_shape():
    evt = fake_fill_webhook("AAPL", 1.0, 10.0)
    assert evt["specversion"] == "1.0" and evt["type"] == "trade.fill"
    assert evt["data"]["symbol"] == "AAPL" and evt["data"]["fill_price"] == 10.0
```

메모
- 테스트 키트는 Gateway 웹훅 수신 형식과 일치하도록 CloudEvents 형태의 페이로드를 제공합니다.
- 최소 스캐폴드는 계약을 유지하기 위해 스텁 노드를 사용하며, 실제 Node Set 구현이 준비되면 교체됩니다.
