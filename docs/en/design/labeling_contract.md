# Labeling Contract & Guardrails (delayed label, no look-forward)

## Purpose

Labeling must define a **contract that structurally prevents leakage** in live trading/serving pipelines. This document specifies label timing, input/output schemas, and no-look-forward guardrails.

## Core Invariants

1. **Labels are not emitted at entry_time=t.**
   - Labels are emitted only after resolved_time=t* (PT/SL hit or timeout).
2. **PT/SL/Time parameters are computed and frozen at t.**
   - Parameters must not change after t to avoid leakage.
3. **Cost/slippage adjustments use only models/parameters known at t.**
4. **Label nodes are learning/evaluation outputs and must not feed orders/decisions.**

## Terminology

- **entry_time (t)**: The position entry (or label anchor) time.
- **resolved_time (t\*)**: The time the label resolves (PT/SL hit or timeout).
- **BarrierSpec**: PT/SL thresholds and units.
- **HorizonSpec**: Timeout guardrails (duration or bar count).
- **LabelEvent**: Resolved label event (for training/evaluation).

## Schema Contract

Shared types live in `qmtl/runtime/labeling/schema.py` and must be frozen at `entry_time`.

```python
from qmtl.runtime.labeling import BarrierSpec, HorizonSpec, LabelEvent, LabelOutcome
```

### BarrierSpec

- `profit_target`: PT threshold (None if unused)
- `stop_loss`: SL threshold (None if unused)
- `mode`: representation (`price` for absolute price barriers, `return` for return-based barriers)
- `frozen_at`: timestamp the parameters were frozen (must match entry_time)

### HorizonSpec

- `max_duration`: max holding duration
- `max_bars`: max bar count
- `frozen_at`: timestamp the parameters were frozen (must match entry_time)

### LabelEvent

- `entry_time`, `resolved_time` must satisfy `resolved_time >= entry_time`.
- If set, `barrier.frozen_at` and `horizon.frozen_at` must equal `entry_time`.
- `outcome` is one of `profit_target`, `stop_loss`, `timeout`.
- `cost_model_id`, `slippage_model_id` record the models used at entry_time.

## No-Look-Forward Guardrails

### 1) Temporal separation

- **Label nodes emit only after `resolved_time`.**
- Label computation reads only past/current data.
- Label outputs must not feed order/decision nodes.

### 2) Parameter freezing

- PT/SL/Timeout parameters are frozen at `entry_time`.
- Changing parameters after `entry_time` is prohibited.

### 3) Cost/slippage rules

- Adjustments use only models/parameters known at `entry_time`.
- Do not apply future-informed dynamic cost models to labels.

## Label Node Guardrails

- Label nodes are learning/evaluation outputs only.
- Do not connect them to order/decision inputs; guard in DAG/nodeset design.
- Tests should block any path from labels to order/risk nodes.

## Follow-up implementation hints

- Label-related nodes/transforms under `qmtl/runtime/nodesets/*`, `qmtl/runtime/indicators/*`, `qmtl/runtime/transforms/*` must honor this contract.
