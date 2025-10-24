# CCXT 스팟 레시피

이 가이드는 내장 CCXT 스팟 Node Set 레시피를 사용해 전략의 시그널 노드를 CCXT 기반 현물 거래소로 라우팅하는 방법을 설명합니다. 레시피는 `NodeSetRecipe` 로 정의되고 레지스트리에 등록돼 공유 계약 테스트와 어댑터 생성을 그대로 상속받습니다. 설계와 작성 지침은 [거래소 Node Set](../architecture/exchange_node_sets.md) 문서를 참고하세요. `tests/qmtl/runtime/nodesets/test_recipe_contracts.py` 의 계약 테스트는 디스크립터 메타데이터, 월드 범위, 포트폴리오/비중 주입이 올바르게 동작하는지 검증합니다.

## 사용법

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

strategy.add_nodes([price, alpha, history, signal, nodeset])  # NodeSet을 직접 추가
```

반환된 Node Set은 디스크립터와 capabilities를 노출해 어댑터가 항상 동기화되도록 합니다.

```python
info = nodeset.describe()      # 포트 + 노드 수
caps = nodeset.capabilities()  # 지원 모드 + 포트폴리오 스코프
```

레시피를 직접 호출하는 방법도 있습니다.

```python
from qmtl.runtime.nodesets.recipes import make_ccxt_spot_nodeset
nodeset = make_ccxt_spot_nodeset(signal_node, "demo-world", exchange_id="binance")
```

## 어댑터 메타데이터와 파라미터

- 레시피는 `CCXT_SPOT_ADAPTER_SPEC` 을 포함하며, 필수 `signal` 포트를 노출하고 선택 파라미터(`sandbox`, `apiKey`, `secret`, `time_in_force`, `reduce_only`)를 전달하는 어댑터를 생성할 수 있습니다.
- 광범위한 DAG 토폴로지에 Node Set을 포함할 때는 어댑터를 동적으로 생성해 사용하세요.

```python
from qmtl.runtime.nodesets.recipes import CCXT_SPOT_ADAPTER_SPEC, build_adapter

CcxtSpotAdapter = build_adapter(CCXT_SPOT_ADAPTER_SPEC)
adapter = CcxtSpotAdapter(exchange_id="binance", sandbox=False)
nodeset = adapter.build({"signal": signal_node}, world_id="demo-world")
```

- 어댑터 구성은 검증됩니다. 예상치 못한 키워드 인자는 `TypeError` 를 발생시키며, 레시피가 확장되더라도 필수 필드는 계속 요구됩니다.

## 분기 예시: 실행 단계에 시세 결합

CCXT 레시피를 확장해 실행 단계에서 시세 스트림을 조인할 수 있습니다. DSL `compose()` 대신 노드를 직접 구성합니다.

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
    # client.post_order(order)  # 프로덕션에서는 클라이언트를 주입해 주문을 전송
    return order

exe = Node(input=[siz, quotes], compute_fn=ccxt_exec_with_quote, name=f"{siz.name}_exec", interval=siz.interval, period=1)
fil = fills()(exe)
pf = portfolio()(fil)
rk = risk()(pf)
tm = timing()(rk)

nodeset = NodeSet((pre, siz, exe, fil, pf, rk, tm))
strategy.add_nodes([price, alpha, history, signal_node, quotes, nodeset])
```

메모
- NodeSet은 블랙박스로 취급하세요. 레시피/어댑터를 통해 내부를 구성하고 전략에서는 단일 단위로 추가/관리합니다.
- `apiKey`/`secret` 을 생략하면 `FakeBrokerageClient` 가 사용되어 시뮬레이션 모드로 실행할 수 있습니다.
- 샌드박스 모드에서는 자격 증명이 필수이며, 누락 시 `RuntimeError` 를 발생시킵니다.
- `time_in_force` 기본값은 `GTC` 입니다. 주문 정책을 조정하려면 `time_in_force="IOC"` 또는 `reduce_only=True` 등을 전달하세요.

전체 예시는 [`qmtl/examples/strategies/ccxt_spot_nodeset_strategy.py`]({{ code_url('qmtl/examples/strategies/ccxt_spot_nodeset_strategy.py') }}) 를 참고하세요.
