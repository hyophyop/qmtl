# qmtl.indicators

Common technical indicator nodes for the QMTL SDK.

- Modules observe the Single Responsibility Principle and keep dependencies minimal.
- When adding new indicators, include unit tests under `tests/`.

Install only when needed:

```bash
pip install qmtl[indicators]
```

Use with:

```python
from qmtl.indicators import sma
```

