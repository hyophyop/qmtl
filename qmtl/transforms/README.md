# qmtl.transforms

Derived transformation nodes for the QMTL SDK.

- Each transform stays focused on a single calculation.
- Add tests for new transforms under `tests/`.

Transforms ship with the core package and do not require a separate install.

Example:

```python
from qmtl.transforms import execution_imbalance_node, rate_of_change

exec_imbalance = execution_imbalance_node(buy_volume, sell_volume)
exec_imbalance_deriv = rate_of_change(exec_imbalance)
```
