# qmtl.transforms

Derived transformation nodes for the QMTL SDK.

- Each transform stays focused on a single calculation.
- Add tests for new transforms under `tests/`.

Transforms ship with the core package and do not require a separate install.

Example:

```python
from qmtl.transforms import rate_of_change, stochastic, angle, order_book_imbalance_node

obi = order_book_imbalance_node(bid_volume_node, ask_volume_node)
obi_derivative = rate_of_change(obi, period=2)
```
