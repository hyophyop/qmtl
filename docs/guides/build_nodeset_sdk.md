# Build NodeSet (SDK)

Compose execution chains programmatically using a small Steps DSL and treat the result as a black‑box `NodeSet`.

## Compose with steps

```python
from qmtl.sdk import StreamInput, Node
from qmtl.nodesets.steps import pretrade, sizing, execution, fills, portfolio, risk, timing, compose

price = StreamInput(interval="60s", period=2)
alpha = Node(input=price, compute_fn=lambda v: 0.1, name="alpha")
signal = Node(input=alpha, compute_fn=lambda v: {"action": "BUY", "size": 1, "symbol": "BTC/USDT"})

# Default chain (all stubs)
nodeset = compose(signal, steps=[pretrade(), sizing(), execution(), fills(), portfolio(), risk(), timing()])
```

## Custom execution step

```python
from qmtl.nodesets.steps import execution

# Define execution compute bound to the sized upstream by the DSL

def ccxt_exec(view, upstream):
    data = view[upstream][upstream.interval]
    if not data:
        return None
    _, order = data[-1]
    # ... route order via client ...
    return order

nodeset = compose(signal, steps=[pretrade(), sizing(), execution(compute_fn=ccxt_exec), fills(), portfolio(), risk(), timing()])
```

Notes
- `compose()` wires steps left‑to‑right and returns a `NodeSet` with `head`/`tail`/`nodes`.
- Missing trailing steps are filled with defaults; extra steps raise.
- Prefer recipes and the registry for built‑in connectors; use the Steps DSL for custom composition.

## Signal blending (optional)

여러 시그널을 단일 시그널로 합치려면 간단한 블렌더 노드를 직접 구성할 수 있습니다.

```python
from qmtl.sdk import Node

signals = [sig_a, sig_b]
weights = [0.6, 0.4]

def blend(view):
    score = 0.0
    for s, w in zip(signals, weights):
        data = view[s][s.interval]
        if not data:
            return None
        v = data[-1][1]
        action = str(v.get("action", "HOLD")).upper()
        size = float(v.get("size", 0.0))
        signed = size if action == "BUY" else (-size if action == "SELL" else 0.0)
        score += w * signed
    if score > 0:
        return {"action": "BUY", "size": score}
    if score < 0:
        return {"action": "SELL", "size": abs(score)}
    return {"action": "HOLD", "size": 0.0}

combined_signal = Node(input=signals, compute_fn=blend, name="signal_blend", interval=sig_a.interval, period=1)
exec_nodeset = compose(combined_signal, steps=[pretrade(), sizing(), execution(), fills(), portfolio(), risk(), timing()])
```

예시 전략: [`qmtl/examples/strategies/multi_signal_blend_strategy.py`]({{ code_url('qmtl/examples/strategies/multi_signal_blend_strategy.py') }})

## Branching inside a Node Set

Compose 브랜칭(합류) 패턴은 DSL의 `compose()` 대신 직접 노드를 생성해 구현합니다. `Node(input=[...])`로 다중 업스트림을 받을 수 있습니다.

```python
from qmtl.sdk import Node
from qmtl.nodesets.base import NodeSet
from qmtl.nodesets.steps import pretrade, sizing, fills, portfolio, risk, timing

# 1) 선형으로 pretrade → sizing 까지 구성하여 sized 업스트림을 확보합니다.
pre = pretrade()(signal)
siz = sizing()(pre)

# 2) 시세/리스크 등 추가 업스트림을 합류시켜 실행 노드를 구성합니다.
def exec_join(view):
    da = view[siz][siz.interval]
    db = view[quotes][quotes.interval]  # 예: 시세 노드
    if not da or not db:
        return None
    _, order = da[-1]
    _, quote = db[-1]
    order = dict(order)
    order.setdefault("price", quote.get("best_ask") or quote.get("close"))
    # ... 브로커 클라이언트로 주문 라우팅 ...
    return order

exe = Node(input=[siz, quotes], compute_fn=exec_join, name=f"{siz.name}_exec", interval=siz.interval, period=1)

# 3) 나머지 스텁들을 이어붙여 마무리합니다.
fil = fills()(exe)
pf = portfolio()(fil)
rk = risk()(pf)
tm = timing()(rk)

nodeset = NodeSet(pretrade=pre, sizing=siz, execution=exe, fills=fil, portfolio=pf, risk=rk, timing=tm)
```

Tips
- DSL은 의도적으로 미니멀합니다. 브랜칭/합류는 레시피에서 직접 노드로 구성하는 것을 권장합니다.
- 어댑터를 사용하면 외부에서 다중 업스트림을 명시적으로 주입할 수 있습니다(예: `signal`, `market_data`).
