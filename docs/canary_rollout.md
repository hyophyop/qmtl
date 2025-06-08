# Canary Rollout Guide

This document explains how to gradually shift traffic between strategy versions using the `DAG‑Mgr` callback endpoint `/callbacks/sentinel-traffic`.

## Adjusting Weights

1. Send an HTTP `POST` request to `/callbacks/sentinel-traffic` on the DAG‑Mgr.
2. The payload must include the `version` identifier and a `weight` between `0` and `1`.
3. On success, the DAG‑Mgr updates its routing table and notifies Gateway to route the specified percentage of traffic to the target version.

Example:

```bash
curl -X POST \ 
     -H 'Content-Type: application/json' \
     -d '{"version": "v1.2.1", "weight": 0.25}' \
     http://dagmgr.internal/callbacks/sentinel-traffic
```

## Monitoring Metrics

* **Gateway metrics:** check `gateway_sentinel_traffic_ratio{version="v1.2.1"}` in Prometheus to confirm the live split.
* **DAG‑Mgr metrics:** monitor `dagmgr_active_version_weight` for each version to ensure the new weight is applied.
* **Alerts:** alert rules under `alert_rules.yml` trigger if traffic weight deviates from the configured value for more than 5 minutes.

Review Grafana dashboards to visualize canary success rates and error budgets while gradually increasing the traffic weight.
