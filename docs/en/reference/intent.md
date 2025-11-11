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
: Emits `target_percent` intents from a single-symbol signal with hysteresis. Outputs order-shaped dicts by default for backward compatibility. Provide either `price_node` or `price_resolver` when `to_order=True` so downstream sizing receives an explicit `price`; the node raises an error if it cannot obtain one.

Example:
```python
from qmtl.runtime.transforms.position_intent import PositionTargetNode, Thresholds

intent_node = PositionTargetNode(
    signal=alpha_node,
    symbol="BTCUSDT",
    thresholds=Thresholds(long_enter=0.7, short_enter=-0.7),
    long_weight=+0.10,
    short_weight=-0.05,
    price_node=price_feed,
)
```

## Intent-first NodeSet recipe

`make_intent_first_nodeset` wraps a `PositionTargetNode` with the standard execution pipeline (pre-trade → sizing → execution → publishing). It accepts a signal node and matching price node, applies hysteresis defaults (`long_enter=0.6`, `short_enter=-0.6`, `long_exit=0.2`, `short_exit=-0.2`), and seeds sizing with `initial_cash=100_000` unless you provide a custom portfolio/account.

```python
from qmtl.runtime.nodesets.recipes import (
    INTENT_FIRST_DEFAULT_THRESHOLDS,
    make_intent_first_nodeset,
)
from qmtl.runtime.sdk.node import StreamInput

signal = StreamInput(tags=["alpha"], interval=60, period=1)
price = StreamInput(tags=["price"], interval=60, period=1)

nodeset = make_intent_first_nodeset(
    signal,
    world_id="demo",
    symbol="BTCUSDT",
    price_node=price,
    thresholds=INTENT_FIRST_DEFAULT_THRESHOLDS,
    long_weight=0.25,
    short_weight=-0.10,
)

strategy.add_nodes([signal, price, nodeset])  # NodeSet is iterable
```

For adapter-style composition use `IntentFirstAdapter` which exposes `signal` and `price` input ports and forwards optional overrides such as `initial_cash` or `execution_model`.

{{ nav_links() }}

