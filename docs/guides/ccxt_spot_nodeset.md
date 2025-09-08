# CCXT Spot Node Set

This guide shows how to route trade signals through the built-in `CcxtSpotNodeSet`,
which wires a strategy's signal node to a CCXT-backed spot exchange.
See [Exchange Node Sets](../architecture/exchange_node_sets.md) for design details.

## Usage

```python
from qmtl.brokerage.ccxt_spot_nodeset import CcxtSpotNodeSet

nodes = CcxtSpotNodeSet.attach(
    signal_node,
    "demo-world",
    exchange_id="binance",
    sandbox=True,
    apiKey=os.getenv("BINANCE_API_KEY"),
    secret=os.getenv("BINANCE_API_SECRET"),
)
```

- When `apiKey`/`secret` are omitted, a `FakeBrokerageClient` is used so the
  strategy can run in simulate mode.
- In sandbox mode credentials are required; missing values raise a `RuntimeError`.
- `time_in_force` defaults to `GTC`; pass `time_in_force="IOC"` or
  `reduce_only=True` to customise orders.

The example strategy at
[`qmtl/examples/strategies/ccxt_spot_nodeset_strategy.py`](../../qmtl/examples/strategies/ccxt_spot_nodeset_strategy.py)
shows a complete setup.
