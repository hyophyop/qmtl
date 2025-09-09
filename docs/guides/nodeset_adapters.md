# Node Set Adapters

Node Set은 내부 노드 구성을 감추는 블랙박스지만, 전략에서 Node처럼 다수의 업스트림을 연결하려면 입력 포트의 스키마를 명시해야 합니다. 이를 위해 `NodeSetAdapter`가 입력/출력 포트를 선언하고 외부 노드들을 내부 체인에 연결(wire)합니다.

## 개념

- PortSpec: 이름/필수 여부/설명으로 구성된 간단한 포트 스펙
- NodeSetDescriptor: Node Set의 입력/출력 포트 집합과 이름
- NodeSetAdapter: `descriptor`를 제공하고, `build(inputs, world_id, options)`로 NodeSet을 구성

## CCXT 예시

```python
from qmtl.nodesets.adapters import CcxtSpotAdapter

adapter = CcxtSpotAdapter(exchange_id="binance", sandbox=False)
nodeset = adapter.build({"signal": signal_node}, world_id="demo")
strategy.add_nodes([price, nodeset])
```

포트
- inputs: `signal` (required) — 트레이드 시그널 스트림
- outputs: `orders` — 실행 노드 출력 (정보용; wiring은 adapter가 수행)

## 커스텀 어댑터

```python
from dataclasses import dataclass
from qmtl.nodesets.adapter import NodeSetAdapter, NodeSetDescriptor, PortSpec
from qmtl.nodesets.base import NodeSet


class MyNodeSetAdapter(NodeSetAdapter):
    descriptor = NodeSetDescriptor(
        name="my_nodeset",
        inputs=(PortSpec("signal"), PortSpec("market_data", required=False)),
        outputs=(PortSpec("orders"),),
    )

    def build(self, inputs: dict, *, world_id: str, options=None) -> NodeSet:
        self.validate_inputs(inputs)
        signal = inputs["signal"]
        quotes = inputs.get("market_data")  # optional

        # 1) 선형으로 pretrade → sizing
        from qmtl.nodesets.steps import pretrade, sizing, fills, portfolio, risk, timing
        from qmtl.sdk import Node
        from qmtl.nodesets.base import NodeSet

        pre = pretrade()(signal)
        siz = sizing()(pre)

        # 2) quotes가 있으면 합류(join) 실행 노드, 없으면 단일 업스트림 실행 노드
        def _exec(view):
            da = view[siz][siz.interval]
            if not da:
                return None
            _, order = da[-1]
            order = dict(order)
            if quotes is not None:
                db = view[quotes][quotes.interval]
                if db:
                    _, q = db[-1]
                    order.setdefault("price", q.get("best_ask") or q.get("close"))
            return order

        exec_inputs = [siz, quotes] if quotes is not None else [siz]
        exe = Node(input=exec_inputs, compute_fn=_exec, name=f"{siz.name}_exec", interval=siz.interval, period=1)
        fil = fills()(exe)
        pf = portfolio()(fil)
        rk = risk()(pf)
        tm = timing()(rk)
        return NodeSet((pre, siz, exe, fil, pf, rk, tm))
```

Notes
- 어댑터는 입력 검증을 강제해 런타임 wiring 오류를 줄입니다.
- Node Set은 여전히 블랙박스이며, 전략은 포트 스펙만 알면 충분합니다.
 - 다중 업스트림(브랜칭)은 어댑터 내부에서 합류 노드를 직접 구성하는 패턴으로 쉽게 확장할 수 있습니다.
