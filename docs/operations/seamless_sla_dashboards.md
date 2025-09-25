---
title: "Seamless SLA Dashboards"
tags: [operations]
author: "QMTL Team"
last_modified: 2025-09-25
---

{{ nav_links() }}

# Seamless SLA Dashboards

> **Status:** The dashboards and alert rules referenced in this runbook are now
> backed by live metrics. Deploy the Jsonnet bundle and wire the alerts in
> production environments; the distributed coordinator and SLA engine ship with
> QMTL v2.

This runbook documents the observability package that accompanies Seamless Data
Provider v2. Changes below supersede the provisional guidance that pre-dated the
implementation tracked in issue #1148.

## Dashboard Bundle

Import `operations/monitoring/seamless_v2.jsonnet` (or the rendered JSON) into
Grafana to provision the three core dashboards:

1. **Seamless SLA Overview** – shows `seamless_sla_deadline_seconds`
   histograms, per-domain latency percentiles, and an error budget gauge.
2. **Backfill Coordinator Health** – visualises lease counts, stale claim
   detections, and `backfill_completion_ratio` trends.
3. **Conformance Quality** – highlights flag totals, schema warnings, and the
   outcome of regression report checks.

Dashboards render successfully once Prometheus scrapes the Seamless runtime. The
bundle depends on the coordinator and SLA metrics described below.

## Metrics and Alerts

The runtime now emits the following metrics:

- `seamless_sla_deadline_seconds` (histogram) – exported by the Seamless data
  provider with `phase` labels for `storage_wait`, `backfill_wait`, `live_wait`,
  and `total`. Alert when the 99th percentile approaches budget.
- `backfill_completion_ratio` – gauge reporting per-lease completion as
  observed by the distributed coordinator.
- `seamless_conformance_flag_total` – counter populated by
  `ConformancePipeline` when normalisation warnings occur.

Alert rules under the `seamless-*` prefix have been added to `alert_rules.yml`.
Ensure PagerDuty and Slack routes are configured in environments where these
alerts should page.

## Tracing and Logging

- **Tracing**: `seamless.pipeline` spans now include `sla.phase` attributes when
  budgets are enforced. Future releases will expand the schema metadata carried
  on these spans.
- **Logging**: the coordinator and SLA layers log to `seamless.backfill` and
  `seamless.sla` respectively. Use these structured logs to correlate alerts
  with lease IDs and offending nodes.

## Runbooks

When an alert fires:

1. Open the Seamless SLA Overview dashboard and inspect the affected domain.
2. Use the Backfill Coordinator Health dashboard to confirm whether leases are
   stuck; reclaim via `scripts/lease_recover.py` if necessary.
3. Check tracing for anomalies in `seamless.pipeline` spans.
4. Escalate according to the ownership matrix in `operations/monitoring.md` and
   document the incident in the Seamless postmortem tracker.

{{ nav_links() }}
