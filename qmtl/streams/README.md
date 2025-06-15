# qmtl.streams

Additional `StreamInput` classes for real-world data sources.

- Each class is independent and focused on a single provider.
- Tests for new streams must be placed under `tests/`.

Install separately:

```bash
pip install qmtl[streams]
```

Example:

```python
from qmtl.streams import BinanceBTCStream
```

