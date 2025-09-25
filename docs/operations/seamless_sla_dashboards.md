---
title: "Seamless SLA Dashboards"
tags: [operations]
author: "QMTL Team"
last_modified: 2025-09-25
---

{{ nav_links() }}

# Seamless SLA Dashboards

> **Status:** Dashboards and alert rules referenced in this runbook are
> placeholders. The distributed coordinator and SLA metrics they rely on are not
> yet available. Keep this document bookmarked for the v2 rollout but avoid
> creating production wiring until the implementation lands.

This runbook captures the intended observability package that will ship with
Seamless Data Provider v2. For now, treat it as design documentation and track
progress in issues #1148–#1152.

## Dashboard Bundle

Import `operations/monitoring/seamless_v2.jsonnet` (or the rendered JSON) into
Grafana once the file is published. The planned bundle will contain three core
dashboards:

1. **Seamless SLA Overview** – shows `seamless_sla_deadline_seconds`
   histograms, per-domain latency percentiles, and an error budget gauge.
2. **Backfill Coordinator Health** – visualises lease counts, stale claim
   detections, and `backfill_completion_ratio` trends.
3. **Conformance Quality** – highlights flag totals, schema warnings, and the
   outcome of regression report checks.

These dashboards do not exist yet. Until they do, rely on existing storage and
backfill monitoring to gauge health.

## Metrics and Alerts

The metrics below are part of the planned rollout. At present only
`seamless_conformance_flag_total` is emitted, and even that requires explicitly
supplying a `ConformancePipeline` instance. Capture the remainder once the
coordinator and SLA engine ship:

- `seamless_sla_deadline_seconds` (histogram) – exported by the Backfill
  Coordinator. Alerts will fire when the 99th percentile exceeds policy.
- `backfill_completion_ratio` – gauge reporting per-lease completion.
- `seamless_schema_validation_failures_total` – counter for strict schema
  violations.

Recommended alert rules will live in `alert_rules.yml` under the `seamless-*`
prefix when they are added. Until then, refrain from wiring PagerDuty or Slack
integrations for non-existent metrics.

## Tracing and Logging

- **Tracing**: planned `seamless.pipeline` spans will eventually add
  `sla.phase`, `backfill.lease_id`, and `schema.validation_mode` attributes. No
  such spans are emitted today.
- **Logging**: future coordinator releases will log to `seamless.backfill` and
  `seamless.sla`. Current builds only emit local debug messages when backfills
  start or complete.

## Runbooks

When alerts are introduced:

1. Open the Seamless SLA Overview dashboard and inspect the affected domain.
2. Use the Backfill Coordinator Health dashboard to confirm whether leases are
   stuck; reclaim via `scripts/lease_recover.py` if necessary.
3. Check tracing for anomalies in `seamless.pipeline` spans.
4. Escalate according to the ownership matrix in `operations/monitoring.md` and
   document the incident in the Seamless postmortem tracker.

{{ nav_links() }}
