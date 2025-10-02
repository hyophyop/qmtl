# Node Set Adapters

Node Set은 내부 노드 구성을 감추는 블랙박스지만, 전략에서 Node처럼 다수의 업스트림을 연결하려면 입력 포트의 스키마를 명시해야 합니다. 이를 위해 `NodeSetAdapter`가 입력/출력 포트를 선언하고 외부 노드들을 내부 체인에 연결(wire)합니다.

## 개념

- PortSpec: 이름/필수 여부/설명으로 구성된 간단한 포트 스펙
- NodeSetDescriptor: Node Set의 입력/출력 포트 집합과 이름
- NodeSetAdapter: `descriptor`를 제공하고, `build(inputs, world_id, options)`로 NodeSet을 구성
- RecipeAdapterSpec + `build_adapter()`: 레시피에서 어댑터 클래스를 자동 생성하고 파라미터 검증/메타데이터를 공유

## CCXT 예시

```python
from qmtl.runtime.nodesets.recipes import CCXT_SPOT_ADAPTER_SPEC, build_adapter

CcxtSpotAdapter = build_adapter(CCXT_SPOT_ADAPTER_SPEC)
adapter = CcxtSpotAdapter(exchange_id="binance", sandbox=False)
nodeset = adapter.build({"signal": signal_node}, world_id="demo")
strategy.add_nodes([price, nodeset])
```

포트
- inputs: `signal` (required) — 트레이드 시그널 스트림
- outputs: `orders` — 실행 노드 출력 (정보용; wiring은 adapter가 수행)
- `adapter.config`는 불변 매핑으로 노출되어 디버깅과 메트릭 태깅에 활용할 수 있습니다.

## 커스텀 어댑터

### `RecipeAdapterSpec`로 자동 생성

```python
from qmtl.runtime.nodesets.adapter import NodeSetDescriptor, PortSpec, AdapterParameter
from qmtl.runtime.nodesets.recipes import RecipeAdapterSpec, build_adapter

CUSTOM_SPEC = RecipeAdapterSpec(
    compose=lambda inputs, world_id, *, risk_cap=1.0: make_custom_nodeset(
        inputs["signal"], world_id, risk_cap=risk_cap
    ),
    descriptor=NodeSetDescriptor(
        name="my_nodeset",
        inputs=(PortSpec("signal"), PortSpec("market_data", required=False)),
        outputs=(PortSpec("orders"),),
    ),
    parameters=(AdapterParameter("risk_cap", annotation=float, default=1.0, required=False),),
)

MyAdapter = build_adapter(CUSTOM_SPEC)
adapter = MyAdapter(risk_cap=0.75)
nodeset = adapter.build({"signal": signal_node, "market_data": quotes}, world_id="demo")
```

### 저수준 API로 직접 구현

```python
from dataclasses import dataclass
from qmtl.runtime.nodesets.adapter import NodeSetAdapter, NodeSetDescriptor, PortSpec
from qmtl.runtime.nodesets.base import NodeSet


class MyNodeSetAdapter(NodeSetAdapter):
    descriptor = NodeSetDescriptor(
        name="my_nodeset",
        inputs=(PortSpec("signal"), PortSpec("market_data", required=False)),
        outputs=(PortSpec("orders"),),
    )

    def build(self, inputs: dict, *, world_id: str, options=None) -> NodeSet:
        self.validate_inputs(inputs)
        # build NodeSet...
        ...
```

Notes
- 어댑터는 입력 검증을 강제해 런타임 wiring 오류를 줄입니다.
- Node Set은 여전히 블랙박스이며, 전략은 포트 스펙만 알면 충분합니다.
 - 다중 업스트림(브랜칭)은 어댑터 내부에서 합류 노드를 직접 구성하는 패턴으로 쉽게 확장할 수 있습니다.
- `RecipeAdapterSpec`를 사용하면 새로운 레시피를 등록할 때마다 어댑터와 테스트 커버리지를 동시에 갱신할 수 있습니다. 새 레시피는 `tests/runtime/nodesets/test_recipe_contracts.py`에 추가하세요.
