# qmtl.transforms

Derived transformation nodes for the QMTL SDK.

- Each transform stays focused on a single calculation.
- Add tests for new transforms under `tests/`.
- Use `identity_transform_node` to collect payloads into a DataFrame for quick inspection.
- Use `scale_transform_node` to multiply an average metric by a constant factor.

Transforms ship with the core package and do not require a separate install.

Example:

```python
from qmtl.transforms import (
    rate_of_change,
    stochastic,
    angle,
    order_book_imbalance_node,
    execution_imbalance_node,
    scale_transform_node,
)

obi = order_book_imbalance_node(bid_volume_node, ask_volume_node)
obi_derivative = rate_of_change(obi, period=2)
exec_imbalance = execution_imbalance_node(buy_volume, sell_volume)
exec_imbalance_deriv = rate_of_change(exec_imbalance)
scaled_metric = scale_transform_node({"average": 2}, factor=3)
```
