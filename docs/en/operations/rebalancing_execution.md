---
title: "Rebalancing Execution Adapter"
tags: [operations, rebalancing]
last_modified: 2025-11-04
---

# Rebalancing Execution Adapter

Convert world rebalancing plans into order payloads that existing pipelines can publish. The adapter does not submit orders; it adds `reduce_only` for negative deltas to safely cut exposure.

## Module

- `qmtl/services/gateway/rebalancing_executor.py`
  - `orders_from_world_plan(plan, options)` → `[order_dict]`
  - `orders_from_strategy_deltas(deltas, options)` → `[order_dict]`

Defaults: `time_in_force="GTC"`, reduce-only for negative deltas.

## Example

```python
from qmtl.services.worldservice.rebalancing import MultiWorldProportionalRebalancer, MultiWorldRebalanceContext
from qmtl.services.gateway.rebalancing_executor import orders_from_world_plan

result = MultiWorldProportionalRebalancer().plan(ctx)
orders = orders_from_world_plan(result.per_world["a"])  # execute per-world
for payload in orders:
    broker_client.post_order(payload)
```

## Routing

- Gateway proxies WorldService `POST /rebalancing/plan`.
  - Body: `MultiWorldRebalanceRequest`
  - Response: `MultiWorldRebalanceResponse`

- Convenience execution endpoint
  - Path: `POST /rebalancing/execute`
  - Body: `MultiWorldRebalanceRequest`
  - Query:
    - `per_strategy=true|false` (default false)
    - `shared_account=true|false` (default false; include `orders_global` using cross-world net deltas)
  - Response: `{ orders_per_world: { world_id: [order_dict...] }, orders_global?: [order_dict...], orders_per_strategy?: [ {world_id, order} ... ] }`

Use `per_world` for execution unless running in a shared-account mode; treat `global_deltas` as an analytical net view otherwise.

{{ nav_links() }}
