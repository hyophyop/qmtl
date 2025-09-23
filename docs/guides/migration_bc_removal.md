---
title: "Migration: Removing Legacy Modes and BC Surfaces"
tags: [migration]
author: "QMTL Team"
last_modified: 2025-09-04
---

{{ nav_links() }}

# Migration: Removing Legacy Modes and Backward Compatibility

This guide summarizes the removal of legacy compatibility layers and shows how to migrate your code.

## Runner API

**Before**

```python
from qmtl import Runner

runner = Runner(...)
runner.backtest(strategy)
```

**After**

```python
from qmtl.runtime.sdk import Runner

runner = Runner(...)
runner.run(strategy, world_id="demo", gateway_url="http://localhost:8000")
# or for local runs
runner.offline(strategy)
```

## CLI

**Before**

```bash
qmtl tools sdk --mode backtest --world-id demo --gateway-url http://localhost:8000
```

**After**

```bash
qmtl tools sdk run --world-id demo --gateway-url http://localhost:8000
qmtl tools sdk offline  # local execution
```

## Gateway `/strategies`

**Before**

```json
{
  "run_type": "backtest",
  "strategy": {...}
}
```

**After**

```json
{
  "world_id": "demo",
  "strategy": {...}
}
```

## Brokerage Imports

**Before**

```python
from qmtl.runtime.brokerage.simple import PerShareFeeModel, VolumeShareSlippageModel
```

**After**

```python
from qmtl.runtime.brokerage import PerShareFeeModel, VolumeShareSlippageModel
```

## Checklist

- [ ] Replace `Runner.backtest`, `Runner.dryrun`, and `Runner.live` with `Runner.run` or `Runner.offline`.
- [ ] Update CLI usage from `--mode` to `run`/`offline` subcommands.
- [ ] Drop `run_type` from Gateway `/strategies` requests and pass `world_id` if needed.
- [ ] Import brokerage helpers from `qmtl.runtime.brokerage`, not `qmtl.runtime.brokerage.simple`.

{{ nav_links() }}

