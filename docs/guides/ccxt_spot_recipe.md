# CCXT Spot Recipe

This guide shows how to route trade signals through the built-in CCXT spot Node Set recipe,
which wires a strategy's signal node to a CCXT-backed spot exchange.
See [Exchange Node Sets](../architecture/exchange_node_sets.md) for design details.

## Usage

```python
from qmtl.nodesets.registry import make

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

Direct recipe import is also available:

```python
from qmtl.nodesets.recipes import make_ccxt_spot_nodeset
nodeset = make_ccxt_spot_nodeset(signal_node, "demo-world", exchange_id="binance")
```

## Branching example: add market data to execution

CCXT 레시피를 확장해 시세 스트림을 실행 단계에 합류시키는 예시입니다. DSL의 `compose()` 대신 직접 노드를 생성해 합류를 구현합니다.

```python
from qmtl.sdk import Node
from qmtl.nodesets.base import NodeSet
from qmtl.nodesets.steps import pretrade, sizing, fills, portfolio, risk, timing

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
    # client.post_order(order)  # 실운영 시 클라이언트 주입 후 주문 전송
    return order

exe = Node(input=[siz, quotes], compute_fn=ccxt_exec_with_quote, name=f"{siz.name}_exec", interval=siz.interval, period=1)
fil = fills()(exe)
pf = portfolio()(fil)
rk = risk()(pf)
tm = timing()(rk)

nodeset = NodeSet(pretrade=pre, sizing=siz, execution=exe, fills=fil, portfolio=pf, risk=rk, timing=tm)
strategy.add_nodes([price, alpha, history, signal_node, quotes, nodeset])
```

Note
- NodeSet은 블랙박스로 사용하세요. 내부는 레시피나 어댑터에서 조합하되, 전략에서는 NodeSet 단위로만 추가/관리합니다.

- When `apiKey`/`secret` are omitted, a `FakeBrokerageClient` is used so the strategy can run in simulate mode.
- In sandbox mode credentials are required; missing values raise a `RuntimeError`.
- `time_in_force` defaults to `GTC`; pass `time_in_force="IOC"` or `reduce_only=True` to customise orders.

The example strategy at
[`qmtl/examples/strategies/ccxt_spot_nodeset_strategy.py`]({{ code_url('qmtl/examples/strategies/ccxt_spot_nodeset_strategy.py') }})
shows a complete setup.

