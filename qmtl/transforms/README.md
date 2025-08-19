# qmtl.transforms

Derived transformation nodes for the QMTL SDK.

- Each transform stays focused on a single calculation.
- Add tests for new transforms under `tests/`.
- Use `identity_transform_node` to collect payloads into a DataFrame for quick inspection.

Transforms ship with the core package and do not require a separate install.

Example:

```python
from qmtl.transforms import rate_of_change, stochastic, angle, order_book_imbalance_node
from qmtl.transforms import execution_imbalance_node, rate_of_change

obi = order_book_imbalance_node(bid_volume_node, ask_volume_node)
obi_derivative = rate_of_change(obi, period=2)
exec_imbalance = execution_imbalance_node(buy_volume, sell_volume)
exec_imbalance_deriv = rate_of_change(exec_imbalance)
```
