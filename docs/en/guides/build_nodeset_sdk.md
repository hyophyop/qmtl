# Build NodeSet (SDK)

Compose execution chains programmatically using a small Steps DSL and treat the result as a black‑box `NodeSet`.
Avoid depending on internal step nodes directly; prefer the metadata helpers
`describe()` and `capabilities()` when you need to inspect a Node Set in tools
or UIs.

## Compose with steps

```python
from qmtl.runtime.sdk import StreamInput, Node
from qmtl.runtime.nodesets.steps import pretrade, sizing, execution, fills, portfolio, risk, timing, compose

price = StreamInput(interval="60s", period=2)
alpha = Node(input=price, compute_fn=lambda v: 0.1, name="alpha")
signal = Node(input=alpha, compute_fn=lambda v: {"action": "BUY", "size": 1, "symbol": "BTC/USDT"})

# Default chain (all stubs)
nodeset = compose(signal, steps=[pretrade(), sizing(), execution(), fills(), portfolio(), risk(), timing()])

# Optional metadata (stable; internals remain a black box)
info = nodeset.describe()
caps = nodeset.capabilities()
```

## Custom execution step

```python
from qmtl.runtime.nodesets.steps import execution

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

To combine multiple signals into one, build a small blender node that merges
the latest upstream values into a single directional score.

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

Example strategy: [`qmtl/examples/strategies/multi_signal_blend_strategy.py`]({{ code_url('qmtl/examples/strategies/multi_signal_blend_strategy.py') }})

## Branching inside a Node Set

For branching and joins, construct nodes directly instead of using `compose()`.
`Node(input=[...])` accepts multiple upstreams.

```python
from qmtl.runtime.sdk import Node
from qmtl.runtime.nodesets.base import NodeSet
from qmtl.runtime.nodesets.steps import pretrade, sizing, fills, portfolio, risk, timing

# 1) Build a linear chain up to `sizing` to obtain the sized upstream.
pre = pretrade()(signal)
siz = sizing()(pre)

# 2) Join additional upstreams (quotes/risk) and build the execution node.
def exec_join(view):
    da = view[siz][siz.interval]
    db = view[quotes][quotes.interval]  # example: quotes node
    if not da or not db:
        return None
    _, order = da[-1]
    _, quote = db[-1]
    order = dict(order)
    order.setdefault("price", quote.get("best_ask") or quote.get("close"))
    # ... route order via brokerage client ...
    return order

exe = Node(input=[siz, quotes], compute_fn=exec_join, name=f"{siz.name}_exec", interval=siz.interval, period=1)

# 3) Append the remaining stubs to finish the chain.
fil = fills()(exe)
pf = portfolio()(fil)
rk = risk()(pf)
tm = timing()(rk)

nodeset = NodeSet((pre, siz, exe, fil, pf, rk, tm))
```

Tips
- The DSL is intentionally minimal. Prefer explicit node construction for
  branch/join patterns in recipes.
- Adapters can expose multiple upstream ports explicitly (for example `signal`,
  `market_data`) and wire them into the internal chain.
