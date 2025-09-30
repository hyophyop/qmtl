---
title: "Canary Rollout Guide"
tags: []
author: "QMTL Team"
last_modified: 2025-08-21
---

{{ nav_links() }}

# Canary Rollout Guide

Traffic splits between strategy versions are adjusted by publishing `sentinel_weight` events to the internal **ControlBus**. Operational tooling should emit these events with the target `version` and desired `weight` (0–1). Gateways consume the ControlBus and relay updates to SDK clients via WebSocket.

## Adjusting Weights

1. Use the Ops tooling to publish a `sentinel_weight` event on the ControlBus.
2. Include the `version` identifier and a `weight` between `0` and `1`.
3. Gateways will apply the new ratio and broadcast the change to connected clients.

## Monitoring Metrics

* **Gateway metrics:** check `gateway_sentinel_traffic_ratio{version="v1.2.1"}` in Prometheus to confirm the live split. The metric is exposed via the Gateway's `/metrics` endpoint and is updated immediately whenever a `sentinel_weight` ControlBus event is processed.
* **Skew guardrail:** monitor `sentinel_skew_seconds{sentinel_id="v1.2.1"}` to ensure Gateway is receiving ControlBus updates quickly relative to the emitter.
* **DAG Manager metrics:** monitor `dagmanager_active_version_weight` for each version to ensure the new weight is applied. This gauge is available from the DAG Manager's `/metrics` endpoint.
* **Alerts:** alert rules under `alert_rules.yml` trigger if traffic weight deviates from the configured value for more than 5 minutes.

Review Grafana dashboards to visualize canary success rates and error budgets while gradually increasing the traffic weight.

{{ nav_links() }}

