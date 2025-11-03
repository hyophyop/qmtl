---
title: "Intent-based Position Targets"
tags: [sdk, intent]
last_modified: 2025-11-04
---

# Intent-based Position Targets

Strategy nodes declare desired positions (intents) instead of issuing orders. The execution layer reconciles to targets using position snapshots.

## Objects

PositionTarget
- symbol: `str`
- target_percent: `float | None` — portfolio weight (±)
- target_qty: `float | None` — absolute quantity (±)
- reason: `str | None`

## Helpers

`to_order_payloads(intents, price_by_symbol=None)`
: Convert a list of `PositionTarget` to order-shaped payloads that carry `target_percent` or `quantity`, compatible with the existing `SizingNode`.

## Nodes

`PositionTargetNode`
: Emits `target_percent` intents from a single-symbol signal with hysteresis. Outputs order-shaped dicts by default for backward compatibility.

Example:
```python
from qmtl.runtime.transforms.position_intent import PositionTargetNode, Thresholds

intent_node = PositionTargetNode(
    signal=alpha_node,
    symbol="BTCUSDT",
    thresholds=Thresholds(long_enter=0.7, short_enter=-0.7),
    long_weight=+0.10,
    short_weight=-0.05,
)
```

{{ nav_links() }}

