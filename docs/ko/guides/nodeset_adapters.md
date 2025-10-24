# Node Set 어댑터

Node Set은 내부 구성을 숨기는 블랙박스입니다. 일반 `Node` 처럼 복수 업스트림을 연결하려면 선언적 포트 스키마가 필요합니다. `NodeSetAdapter` 는 입력/출력 포트를 선언하고 외부 노드를 내부 체인에 연결합니다.

## 핵심 개념

- PortSpec: 이름/필수 여부/설명을 담은 단순 사양
- NodeSetDescriptor: Node Set의 이름과 포트 집합을 정의
- NodeSetAdapter: `descriptor` 와 `build(inputs, world_id, options)` 를 노출
- RecipeAdapterSpec + `build_adapter()`: 레시피에서 어댑터 클래스를 자동 생성하며 파라미터 검증과 메타데이터를 공유

## CCXT 예시

```python
from qmtl.runtime.nodesets.recipes import CCXT_SPOT_ADAPTER_SPEC, build_adapter

CcxtSpotAdapter = build_adapter(CCXT_SPOT_ADAPTER_SPEC)
adapter = CcxtSpotAdapter(exchange_id="binance", sandbox=False)
nodeset = adapter.build({"signal": signal_node}, world_id="demo")
strategy.add_nodes([price, nodeset])
```

포트 정의
- 입력: `signal` (필수) — 트레이드 시그널 스트림
- 출력: `orders` — 실행 결과(정보용; 실제 연결은 내부 처리)
- `adapter.config` 는 디버깅과 메트릭 태깅을 위한 불변 매핑입니다.

## 커스텀 어댑터

### `RecipeAdapterSpec` 으로 자동 생성

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

### 로우레벨 API로 직접 구현

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
        # NodeSet 구성...
        ...
```

메모
- 어댑터는 입력 검증을 강제해 런타임 배선 오류를 줄여줍니다.
- Node Set은 블랙박스 상태를 유지하며, 전략은 포트 사양만 알면 됩니다.
- 어댑터는 내부적으로 조인 노드를 구성해 다중 업스트림 패턴을 지원할 수 있습니다.
- `RecipeAdapterSpec` 을 사용하면 새로운 레시피가 추가될 때도 어댑터와 계약 테스트가 항상 동기화됩니다. 관련 테스트는 `tests/qmtl/runtime/nodesets/test_recipe_contracts.py` 에서 확장하세요.
