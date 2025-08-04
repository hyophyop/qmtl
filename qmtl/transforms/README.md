# qmtl.transforms

Derived transformation nodes for the QMTL SDK.

- Each transform stays focused on a single calculation.
- Add tests for new transforms under `tests/`.

Transforms ship with the core package and do not require a separate install.

Example:

```python
from qmtl.transforms import rate_of_change, stochastic, angle
```
