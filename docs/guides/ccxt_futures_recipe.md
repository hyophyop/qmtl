# CCXT Futures Recipe

This guide explains how to route trade signals through the CCXT futures Node Set recipe,
which connects a strategy to a perpetual futures exchange (Binance USDT-M by default). The recipe
leverages `NodeSetRecipe` for consistent composition and is registered for discovery so adapters and tests remain aligned.
Refer to [Exchange Node Sets](../architecture/exchange_node_sets.md) for architecture context. Contract tests in
`tests/runtime/nodesets/test_recipe_contracts.py` exercise this recipe alongside CCXT spot, ensuring the sizing/portfolio
injection and node count remain stable.

## Usage

```python
import os

from qmtl.runtime.nodesets.registry import make

nodeset = make(
    "ccxt_futures",
    signal_node,
    "demo-world",
    exchange_id="binanceusdm",
    sandbox=True,
    apiKey=os.getenv("BINANCE_FUT_API_KEY"),
    secret=os.getenv("BINANCE_FUT_API_SECRET"),
    leverage=5,
    margin_mode="cross",
    hedge_mode=True,
)

strategy.add_nodes([price, alpha, history, signal_node, nodeset])
```

The Node Set exposes metadata for adapter/tooling integration:

```python
info = nodeset.describe()       # node count + descriptor (currently None)
caps = nodeset.capabilities()  # ['simulate', 'paper', 'live'] scope
```

You can also import the recipe directly:

```python
import os

from qmtl.runtime.nodesets.recipes import make_ccxt_futures_nodeset

nodeset = make_ccxt_futures_nodeset(
    signal_node,
    "demo-world",
    exchange_id="binanceusdm",
    leverage=10,
    reduce_only=True,
)
```

## Order parameter propagation

The futures recipe mirrors the spot chain (pretrade → sizing → execution → order publish) but
adds futures-specific defaults:

- `time_in_force` defaults to `GTC`; override via the recipe arguments.
- Setting `reduce_only=True` injects `reduce_only` into the published orders.
- `leverage` applies both as a per-order field and, when supported, via CCXT's `set_leverage` API.
- `margin_mode` (`"cross"` by default) and `hedge_mode` are applied best-effort during client initialisation.

Signal nodes should emit dictionaries containing at least `action`, `size`, and `symbol`. The
sizing node converts `size` values into quantities using the shared portfolio configuration.

## Example strategy

[`qmtl/examples/strategies/ccxt_futures_nodeset_strategy.py`]({{ code_url('qmtl/examples/strategies/ccxt_futures_nodeset_strategy.py') }})
demonstrates wiring a simple momentum signal through the futures recipe. For an imperative demo
that places a Binance Futures Testnet order, see
[`qmtl/examples/brokerage_demo/ccxt_binance_futures_nodeset_demo.py`]({{ code_url('qmtl/examples/brokerage_demo/ccxt_binance_futures_nodeset_demo.py') }}).

## Notes

- When `apiKey`/`secret` are omitted the recipe runs in simulate mode using a `FakeBrokerageClient`.
- Sandbox/testnet mode requires credentials; missing keys raise a `RuntimeError`.
- Binance USDT-M symbols use the `BTC/USDT` form. Exchanges that require suffixes (e.g. `BTC/USDT:USDT`)
  should be handled in the signal/order payload and documented per strategy.
- Fill ingestion remains a stub; integrate exchange webhooks or polling in follow-up work if needed.
- Extending the recipe? Add your variant to `tests/runtime/nodesets/test_recipe_contracts.py` so chain length,
  modes, and portfolio injection keep their guarantees.
