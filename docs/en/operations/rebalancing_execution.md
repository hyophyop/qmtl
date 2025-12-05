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
- `overlay` requires `overlay.instrument_by_world` + `overlay.price_by_symbol` and returns `overlay_deltas`; `hybrid` is not implemented and returns HTTP 501.

Use `per_world` for execution unless running in a shared-account mode; treat `global_deltas` as an analytical net view otherwise. When `shared_account=true` the Gateway emits a `scope="global"` batch alongside the per-world batches so downstream consumers can decide which aggregation level to honour.

### Shared-account safety policy

The Gateway disables shared-account netting by default. Operators must set `gateway.shared_account_policy.enabled=true` and configure the thresholds below before execution is allowed.

- `max_gross_notional`: upper bound on the summed absolute notional of the global orders.
- `max_net_notional`: upper bound on the residual notional after netting (absolute value of the signed sum).
- `min_margin_headroom`: minimum margin buffer ratio (`0.0-1.0`) that must remain after the orders execute.

If a check fails the Gateway responds with HTTP 422 and `E_SHARED_ACCOUNT_POLICY`, including computed metrics (`gross_notional`, `net_notional`, `margin_headroom`, `total_equity`) under the `context` key. Requests made while the toggle is off return HTTP 403 `E_SHARED_ACCOUNT_DISABLED`.

## Submission semantics

- **Live guard:** when `submit=true` the request must include header `X-Allow-Live: true` (unless `enforce_live_guard` is disabled in configuration). Requests without the header are rejected with HTTP 403.
- **Venue policies:** lot sizes, minimum trade notional and venue capabilities are applied before submission. Reduce-only flags are omitted for venues that do not support them and venues that require IOC will have `time_in_force="IOC"` set automatically.
- **Metrics:** each submitted batch increments Prometheus counters/gauges (`rebalance_batches_submitted_total`, `rebalance_last_batch_size`, `rebalance_reduce_only_ratio`) labelled by `world_id` and `scope`.
- **ControlBus fan-out:** WorldService publishes `rebalancing_planned` events that Gateway relays via the WebSocket `rebalancing` topic (`rebalancing.planned`) while updating plan-level metrics (`rebalance_plans_observed_total`, `rebalance_plan_last_delta_count`, `rebalance_plan_execution_attempts_total`, `rebalance_plan_execution_failures_total`).
- **Audit trail:** the Gateway records an `append_event` entry under `rebalance:<world_id>` summarising order counts and reduce-only ratios for each batch.
- **Commit log:** submitted batches are written to the commit log as `("gateway.rebalance", timestamp_ms, batch_id, payload)` where `payload` contains the batch scope, orders and metadata (shared-account flag, reduce-only ratio, mode).

## 2‑Phase apply / rollback checkpoints

- Rebalancing applies are tracked with `run_id`/`etag` like world activation; review `/worlds/{id}/apply` logs alongside `rebalance:<world_id>` audit entries.
- CLI examples  
  - Plan: `uv run qmtl world rebalance-plan --world-id demo_world --target w1=0.6,w2=0.4 --output json`  
  - Apply: `uv run qmtl world rebalance-apply --world-id demo_world --target w1=0.6,w2=0.4 --run-id $(uuidgen) --etag <etag> --submit=true`
- On failure, `rebalance_plan_execution_failures_total` increments and the batch remains in Commit Log/Audit; re-apply with the same `run_id` or rollback via `activation set` before retrying.

{{ nav_links() }}
