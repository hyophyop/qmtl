---
title: "Migration: Removing Legacy Modes and BC Surfaces"
tags: [migration]
author: "QMTL Team"
last_modified: 2025-09-04
---

{{ nav_links() }}

# Migration: Removing Legacy Modes and Backward Compatibility

This guide summarizes the removal of legacy compatibility layers and shows how to migrate your code.

## Runner API (single entrypoint)

**Before (legacy, removed)**: multiple entrypoints (`backtest/dryrun/live/run/offline`)

**After (submit-only)**

```python
from qmtl.runtime.sdk import Runner

result = Runner.submit(MyStrategy, world="demo", preset="moderate")
print(result.status, result.world)
```

## CLI

```bash
# Submit strategy with preset policy
qmtl submit my_strategy.py --world demo --preset aggressive

# Create/inspect worlds with preset policies
qmtl world create demo --policy conservative
qmtl world info demo

# Operator commands require --admin
qmtl --admin gw --config qmtl.yml
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

- [ ] Replace all `Runner.backtest`/`Runner.dryrun`/`Runner.live`/`Runner.run`/`Runner.offline` with `Runner.submit(...)`.
- [ ] CLI: use `qmtl submit [--preset <name>]` instead of legacy `service sdk run/offline`.
- [ ] Configure world policy via `qmtl world create --policy <preset>` or `POST /worlds/{id}/policies` (preset + overrides supported).
- [ ] Inspect world policy via `qmtl world info` or `GET /worlds/{id}/describe` (returns preset, version, human-readable summary).
- [ ] Drop `run_type` and client-selected modes from Gateway `/strategies` requests; rely on `world_id` and WS governance (`effective_mode`).
- [ ] Import brokerage helpers from `qmtl.runtime.brokerage`, not `qmtl.runtime.brokerage.simple`.

{{ nav_links() }}
