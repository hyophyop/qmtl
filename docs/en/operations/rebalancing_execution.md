---
title: "Rebalancing Execution Adapter"
tags: [operations, rebalancing]
last_modified: 2025-11-04
---

# Rebalancing Execution Adapter

Convert world rebalancing plans into order payloads that existing pipelines can publish. When invoked with `submit=true` the Gateway pushes batches to the commit log so the normal StrategyManager/CommitLog path can route the orders to downstream brokers. Dry-run behaviour (without `submit=true`) is unchanged and still returns the calculated orders without side effects.

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
    - `submit=true|false` (default false; submit batches via CommitLog)
  - Response: `{ orders_per_world: { world_id: [order_dict...] }, orders_global?: [order_dict...], orders_per_strategy?: [ {world_id, order} ... ] }`

Mode selection
- Set `mode` in the request body (`scaling` default).
- `overlay`/`hybrid` are not implemented yet and will raise NotImplementedError.

Use `per_world` for execution unless running in a shared-account mode; treat `global_deltas` as an analytical net view otherwise. When `shared_account=true` the Gateway emits a `scope="global"` batch alongside the per-world batches so downstream consumers can decide which aggregation level to honour.

## Submission semantics

- **Live guard:** when `submit=true` the request must include header `X-Allow-Live: true` (unless `enforce_live_guard` is disabled in configuration). Requests without the header are rejected with HTTP 403.
- **Venue policies:** lot sizes, minimum trade notional and venue capabilities are applied before submission. Reduce-only flags are omitted for venues that do not support them and venues that require IOC will have `time_in_force="IOC"` set automatically.
- **Metrics:** each submitted batch increments Prometheus counters/gauges (`rebalance_batches_submitted_total`, `rebalance_last_batch_size`, `rebalance_reduce_only_ratio`) labelled by `world_id` and `scope`.
- **ControlBus fan-out:** WorldService publishes `rebalancing_planned` events that Gateway relays via the WebSocket `rebalancing` topic (`rebalancing.planned`) while updating plan-level metrics (`rebalance_plans_observed_total`, `rebalance_plan_last_delta_count`, `rebalance_plan_execution_attempts_total`, `rebalance_plan_execution_failures_total`).
- **Audit trail:** the Gateway records an `append_event` entry under `rebalance:<world_id>` summarising order counts and reduce-only ratios for each batch.
- **Commit log:** submitted batches are written to the commit log as `("gateway.rebalance", timestamp_ms, batch_id, payload)` where `payload` contains the batch scope, orders and metadata (shared-account flag, reduce-only ratio, mode).

{{ nav_links() }}
