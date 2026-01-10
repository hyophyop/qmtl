# Core Loop Observability Minimum Set

This guide summarizes the minimum observability fields and lookup locations
needed to trace core loop flows across Gateway (GW), WorldService (WS), and
DAG Manager (DM). For architecture context, see
[Gateway](../architecture/gateway.md),
[WorldService](../architecture/worldservice.md),
and [DAG Manager](../architecture/dag-manager.md).

## Minimum common fields

Treat the following fields consistently across logs, metrics, and traces.

* `world_id`
* `execution_domain`
* `run_id`
* `etag`
* (when available) `strategy_id`, `request_id`, `decision_id`

## Where to look in logs

| Service | Key event | Fields | Notes |
| --- | --- | --- | --- |
| GW | `dagmanager_diff_dispatch` | `world_id`, `execution_domain`, `strategy_id` | Diff request dispatch |
| GW | `activation_update_received` | `world_id`, `run_id`, `etag`, `strategy_id` | ControlBus activation update received |
| GW | `rebalancing_planned_received` | `world_id`, `run_id` | Rebalancing plan received |
| WS | `apply_requested` / `apply_stage_*` | `world_id`, `run_id` | Apply stage progression |
| WS | `activation_update_published` / `activation_state_update_published` | `world_id`, `run_id`, `etag`, `strategy_id` | Activation event published |
| WS | `evaluation_decision_completed` | `world_id`, `run_id`, `strategy_id` | Evaluation/decision finalized |
| DM | `diff_request_received` | `world_id`, `execution_domain`, `strategy_id` | Diff request received |

Search WS/GW logs by `run_id` and tie DM activity via `execution_domain` to
reconstruct the full path quickly.

## Where to look in metrics

* **WorldService**
  * `world_apply_run_total` (`world_id`, `run_id`, `status`)
  * `world_apply_failure_total` (`world_id`, `run_id`, `stage`)
* **Gateway**
  * `controlbus_apply_ack_total` (`world_id`, `run_id`, `phase`)
  * `controlbus_apply_ack_latency_ms` (`world_id`, `run_id`, `phase`)

Use metrics to spot rate/latency changes, then pivot to logs with the same
`run_id` for root-cause analysis.

## Where to look in tracing

* `dagmanager_diff_dispatch` / `diff_request_received` spans carry
  `world_id`, `execution_domain`, `strategy_id` attributes.
* WS evaluation/apply spans record `world_id`, `run_id`, `strategy_id`, and
  activation publishing adds `etag`.

Filter spans by the shared attributes to follow a single `run_id` across
service boundaries and identify latency hotspots.
