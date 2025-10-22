# Bracket Order Helper

The `BracketOrder` utility submits an entry order and, once filled, manages
linked take-profit and stop-loss exits as an `OCOOrder`.

Example usage:

```python
from qmtl.runtime.brokerage import BracketOrder, Order, OrderType, TimeInForce

entry = Order(
    symbol="AAPL",
    quantity=100,
    price=100.0,
    type=OrderType.LIMIT,
    tif=TimeInForce.GTC,
    limit_price=100.0,
)
take_profit = Order(
    symbol="AAPL",
    quantity=-100,
    price=100.0,
    type=OrderType.LIMIT,
    tif=TimeInForce.GTC,
    limit_price=110.0,
)
stop_loss = Order(
    symbol="AAPL",
    quantity=-100,
    price=100.0,
    type=OrderType.STOP,
    tif=TimeInForce.GTC,
    stop_price=90.0,
)
bracket = BracketOrder(entry, take_profit, stop_loss)
```

See `qmtl/examples/brokerage_demo/bracket_demo.py` for a runnable example.
