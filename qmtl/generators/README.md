# qmtl.generators

Synthetic data generators that extend `qmtl.sdk`.

- Keep each generator self-contained in line with the Single Responsibility Principle.
- All generators must have accompanying tests under `tests/`.

Install the extension:

```bash
pip install qmtl[generators]
```

Usage example:

```python
from qmtl.generators import GarchInput
```

