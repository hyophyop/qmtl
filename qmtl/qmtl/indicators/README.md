# qmtl.indicators

Common technical indicator nodes for the QMTL SDK.

- Modules observe the Single Responsibility Principle and keep dependencies minimal.
- When adding new indicators, include unit tests under `tests/`.

The indicators module ships with the core package; no extra install is required.

Use with:

```python
from qmtl.indicators import sma
```

## Custom indicators with history

Wrap any function returning an ``{"alpha": value}`` mapping with
``alpha_indicator_with_history`` to keep a sliding window of recent alpha
values:

```python
from qmtl.indicators import alpha_indicator_with_history

def my_alpha(view):
    return {"alpha": 42}

node = alpha_indicator_with_history(my_alpha, window=30)
```

The resulting node emits a list of the latest ``window`` alpha values.

