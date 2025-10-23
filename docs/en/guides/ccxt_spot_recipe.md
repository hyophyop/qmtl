# CCXT Spot Recipe

This guide shows how to route trade signals through the built-in CCXT spot Node Set recipe,
which wires a strategy's signal node to a CCXT-backed spot exchange. The recipe is defined with
`NodeSetRecipe` and registered for discovery so it inherits shared contract tests and adapter generation.
See [Exchange Node Sets](../architecture/exchange_node_sets.md) for design details and authoring guidance.
Contract coverage in `tests/qmtl/runtime/nodesets/test_recipe_contracts.py` verifies descriptor metadata, world scoping,
and portfolio/weight injection for this recipe.

## Usage

```python
from qmtl.runtime.nodesets.registry import make

nodeset = make(
    "ccxt_spot",
    signal_node,
    "demo-world",
    exchange_id="binance",
    sandbox=True,
    apiKey=os.getenv("BINANCE_API_KEY"),
    secret=os.getenv("BINANCE_API_SECRET"),
)

strategy.add_nodes([price, alpha, history, signal, nodeset])  # NodeSet accepted directly
```

The returned Node Set exposes its descriptor and capabilities so adapters stay in sync:

```python
info = nodeset.describe()       # ports + node count
caps = nodeset.capabilities()  # modes + portfolio scope
```

Direct recipe import is also available:

```python
from qmtl.runtime.nodesets.recipes import make_ccxt_spot_nodeset
nodeset = make_ccxt_spot_nodeset(signal_node, "demo-world", exchange_id="binance")
```

## Adapter metadata and parameters

- The recipe ships with `CCXT_SPOT_ADAPTER_SPEC`, which can generate an adapter that exposes a single required `signal` port and forwards optional parameters (`sandbox`, `apiKey`, `secret`, `time_in_force`, `reduce_only`).
- Build the adapter dynamically when embedding the Node Set into broader DAG topologies:

```python
from qmtl.runtime.nodesets.recipes import CCXT_SPOT_ADAPTER_SPEC, build_adapter

CcxtSpotAdapter = build_adapter(CCXT_SPOT_ADAPTER_SPEC)
adapter = CcxtSpotAdapter(exchange_id="binance", sandbox=False)
nodeset = adapter.build({"signal": signal_node}, world_id="demo-world")
```

- Adapter configuration is validated: unexpected keyword arguments raise `TypeError` and required fields remain mandatory even if the recipe evolves.

## Branching example: add market data to execution

Extend the CCXT recipe by joining a quote stream at the execution step. Build
nodes directly rather than using the DSL `compose()`.

```python
from qmtl.runtime.sdk import Node
from qmtl.runtime.nodesets.base import NodeSet
from qmtl.runtime.nodesets.steps import pretrade, sizing, fills, portfolio, risk, timing

pre = pretrade()(signal_node)
siz = sizing()(pre)

def ccxt_exec_with_quote(view):
    da = view[siz][siz.interval]
    db = view[quotes][quotes.interval]
    if not da or not db:
        return None
    _, order = da[-1]
    _, q = db[-1]
    order = dict(order)
    order.setdefault("price", q.get("best_ask") or q.get("close"))
    # client.post_order(order)  # inject client and send order in production
    return order

exe = Node(input=[siz, quotes], compute_fn=ccxt_exec_with_quote, name=f"{siz.name}_exec", interval=siz.interval, period=1)
fil = fills()(exe)
pf = portfolio()(fil)
rk = risk()(pf)
tm = timing()(rk)

nodeset = NodeSet((pre, siz, exe, fil, pf, rk, tm))
strategy.add_nodes([price, alpha, history, signal_node, quotes, nodeset])
```

Note
- Treat the NodeSet as a black box. Compose internals via recipes/adapters and
  add/manage it as a single unit in strategies.

- When `apiKey`/`secret` are omitted, a `FakeBrokerageClient` is used so the strategy can run in simulate mode.
- In sandbox mode credentials are required; missing values raise a `RuntimeError`.
- `time_in_force` defaults to `GTC`; pass `time_in_force="IOC"` or `reduce_only=True` to customise orders.

The example strategy at
[`qmtl/examples/strategies/ccxt_spot_nodeset_strategy.py`]({{ code_url('qmtl/examples/strategies/ccxt_spot_nodeset_strategy.py') }})
shows a complete setup.
