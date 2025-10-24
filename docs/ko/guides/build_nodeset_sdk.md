# NodeSet 구성하기 (SDK)

소규모 Steps DSL을 사용해 실행 체인을 프로그래밍 방식으로 조합하고 결과를 블랙박스 `NodeSet` 으로 다룹니다. 내부 스텝 노드에 직접 의존하지 말고, 도구나 UI에서 Node Set을 살펴봐야 할 때는 `describe()` 와 `capabilities()` 같은 메타데이터 헬퍼를 활용하세요.

## Steps로 구성하기

```python
from qmtl.runtime.sdk import StreamInput, Node
from qmtl.runtime.nodesets.steps import pretrade, sizing, execution, fills, portfolio, risk, timing, compose

price = StreamInput(interval="60s", period=2)
alpha = Node(input=price, compute_fn=lambda v: 0.1, name="alpha")
signal = Node(input=alpha, compute_fn=lambda v: {"action": "BUY", "size": 1, "symbol": "BTC/USDT"})

# 기본 체인 (모든 스텁 포함)
nodeset = compose(signal, steps=[pretrade(), sizing(), execution(), fills(), portfolio(), risk(), timing()])

# 선택적 메타데이터(안정적 API; 내부 구현은 블랙박스 유지)
info = nodeset.describe()
caps = nodeset.capabilities()
```

## 커스텀 실행 단계

```python
from qmtl.runtime.nodesets.steps import execution

# DSL이 제공하는 사이징 완료 업스트림에 바인딩된 실행 로직 정의

def ccxt_exec(view, upstream):
    data = view[upstream][upstream.interval]
    if not data:
        return None
    _, order = data[-1]
    # ... 클라이언트를 통해 주문 라우팅 ...
    return order

nodeset = compose(signal, steps=[pretrade(), sizing(), execution(compute_fn=ccxt_exec), fills(), portfolio(), risk(), timing()])
```

메모
- `compose()` 는 왼쪽에서 오른쪽으로 스텝을 연결하고 `head`/`tail`/`nodes` 속성이 있는 `NodeSet` 을 반환합니다.
- 누락된 후행 스텝은 기본값으로 채워지며, 스텝이 과다하면 예외가 발생합니다.
- 내장 커넥터는 레시피와 레지스트리를 우선 사용하고, DSL은 커스텀 조합이 필요할 때 활용하세요.

## 신호 블렌딩(선택)

복수의 시그널을 하나로 합치려면, 최신 업스트림 값을 단일 방향 점수로 합치는 작은 블렌더 노드를 구성합니다.

```python
from qmtl.runtime.sdk import Node

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

## Node Set 내부 분기 처리

분기와 조인을 구현할 때는 `compose()` 대신 노드를 직접 구성하세요. `Node(input=[...])` 는 복수 업스트림을 지원합니다.

```python
from qmtl.runtime.sdk import Node
from qmtl.runtime.nodesets.base import NodeSet
from qmtl.runtime.nodesets.steps import pretrade, sizing, fills, portfolio, risk, timing

# 1) `sizing` 까지 선형 체인을 구축해 사이징된 업스트림을 확보합니다.
pre = pretrade()(signal)
siz = sizing()(pre)

# 2) 추가 업스트림(예: 시세/리스크)을 조인하고 실행 노드를 구성합니다.
def exec_join(view):
    da = view[siz][siz.interval]
    db = view[quotes][quotes.interval]
    if not da or not db:
        return None
    _, order = da[-1]
    _, quote = db[-1]
    order = dict(order)
    order.setdefault("price", quote.get("best_ask") or quote.get("close"))
    # ... 브로커리지 클라이언트를 통해 주문 라우팅 ...
    return order

exe = Node(input=[siz, quotes], compute_fn=exec_join, name=f"{siz.name}_exec", interval=siz.interval, period=1)

# 3) 남은 스텁을 이어 체인을 마무리합니다.
fil = fills()(exe)
pf = portfolio()(fil)
rk = risk()(pf)
tm = timing()(rk)

nodeset = NodeSet((pre, siz, exe, fil, pf, rk, tm))
```

팁
- DSL은 의도적으로 최소화되어 있습니다. 레시피에서 분기/조인이 필요하면 명시적으로 노드를 구성하는 편이 낫습니다.
- 어댑터는 복수 업스트림 포트를 명시적으로 노출(예: `signal`, `market_data`)하고 내부 체인에 연결할 수 있습니다.
