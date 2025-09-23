# Strategy Callbacks

QMTL strategies can react to lifecycle events via optional callbacks on the
`Strategy` base class. These hooks enable stateful position management without
embedding imperative logic in the DAG nodes.

## Available Hooks

* `on_start()` – invoked once before the strategy begins processing.
* `on_signal(signal)` – handle trade signal dictionaries such as those created
  by `buy_signal`.
* `on_fill(order, fill)` – update state when an order receives a fill.
* `on_error(error)` – called if the runner encounters an unrecoverable error.
* `on_finish()` – executed after the run completes successfully.

## Example

```python
from qmtl.runtime.sdk import Strategy, buy_signal

class MyStrategy(Strategy):
    def __init__(self):
        super().__init__(default_interval="1m", default_period=1)
        self.in_position = False

    def on_signal(self, signal):
        if signal.get("action") == "BUY":
            self.in_position = True

    def on_fill(self, order, fill):
        self.in_position = order.get("action") == "BUY"

    def generate(self, price):
        return buy_signal(price > 0)
```
