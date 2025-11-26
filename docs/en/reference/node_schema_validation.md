---
title: "Node DataFrame Schema Validation"
tags: []
author: "QMTL Team"
last_modified: 2025-09-08
---

{{ nav_links() }}

# Node DataFrame Schema Validation

Nodes may declare an `expected_schema` to validate incoming pandas
`DataFrame` payloads. Schemas map column names to dtype strings and are
checked automatically when data is fed into a node.

## Declaring Schemas

```python
from qmtl.runtime.sdk import SourceNode

price = SourceNode(
    interval="1s",
    period=1,
    expected_schema={"ts": "int64", "close": "float64"},
)
```

## Enforcement Modes

Schema checking is controlled by the Runner via the
`schema_enforcement` flag. Available modes are:

- `fail` (default): raise `NodeValidationError` on mismatch
- `warn`: log a warning but continue
- `off`: skip validation

```python
from qmtl.runtime.sdk import Runner, Mode

Runner.submit(MyStrategy, mode=Mode.BACKTEST, schema_enforcement="warn")
```

## Error Messages

In `fail` mode, errors include node context for easier debugging:

```
Node abc123: missing columns: ['close']
```

{{ nav_links() }}
