# Node Set Adapters

A Node Set is a black box that hides its internal composition. When you want to
connect multiple upstreams to it (like a regular `Node`), you need a declarative
port schema. `NodeSetAdapter` declares input/output ports and wires external
nodes to the internal chain.

## Concepts

- PortSpec: simple spec with name/required/description
- NodeSetDescriptor: name and port sets for a Node Set
- NodeSetAdapter: exposes `descriptor` and `build(inputs, world_id, options)`
- RecipeAdapterSpec + `build_adapter()`: auto‑generates adapter classes from recipes with parameter validation and shared metadata

## CCXT example

```python
from qmtl.runtime.nodesets.recipes import CCXT_SPOT_ADAPTER_SPEC, build_adapter

CcxtSpotAdapter = build_adapter(CCXT_SPOT_ADAPTER_SPEC)
adapter = CcxtSpotAdapter(exchange_id="binance", sandbox=False)
nodeset = adapter.build({"signal": signal_node}, world_id="demo")
strategy.add_nodes([price, nodeset])
```

Ports
- inputs: `signal` (required) — trade signal stream
- outputs: `orders` — execution output (informational; wiring handled internally)
- `adapter.config` is an immutable mapping for debugging and metric tagging.

## Custom adapters

### Auto‑generate with `RecipeAdapterSpec`

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

### Implement with the low‑level API

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
- Adapters enforce input validation, reducing wiring errors at runtime.
- The Node Set remains a black box; strategies only need the port spec.
- Adapters can build join nodes internally to support multi‑upstream patterns.
- Using `RecipeAdapterSpec` keeps adapters and contract tests in sync when new
  recipes are added. Expand coverage in
  `tests/qmtl/runtime/nodesets/test_recipe_contracts.py`.
