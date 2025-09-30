# qmtl.runtime.generators

Synthetic data generators that extend `qmtl.runtime.sdk`.

- Keep each generator self-contained in line with the Single Responsibility Principle.
- All generators must have accompanying tests under `tests/`.

Generators are included with the main package and require no extra installation.

Usage example:

```python
from qmtl.runtime.generators import GarchInput
```

