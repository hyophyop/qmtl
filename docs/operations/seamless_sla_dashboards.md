---
title: "Seamless SLA Dashboards"
tags: [operations]
author: "QMTL Team"
last_modified: 2025-09-25
---

{{ nav_links() }}

# Seamless SLA Dashboards

This runbook describes the observability package that ships with Seamless Data
Provider v2. Use it to validate SLA health, coordinate backfill responses, and
escalate when deadlines slip.

## Dashboard Bundle

Import `operations/monitoring/seamless_v2.jsonnet` (or the rendered JSON) into
Grafana. The bundle contains three core dashboards:

1. **Seamless SLA Overview** – shows `seamless_sla_deadline_seconds`
   histograms, per-domain latency percentiles, and an error budget gauge.
2. **Backfill Coordinator Health** – visualises lease counts, stale claim
   detections, and `backfill_completion_ratio` trends.
3. **Conformance Quality** – highlights flag totals, schema warnings, and the
   outcome of regression report checks.

All panels default to 6-hour windows with automatic annotations for alert
firings, enabling rapid triage.

## Metrics and Alerts

The following metrics must be scraped by Prometheus:

- `seamless_sla_deadline_seconds` (histogram) – exported by the Backfill
  Coordinator. Alerts fire when the 99th percentile exceeds policy.
- `seamless_conformance_flag_total` – counter broken down by flag type and
  strategy. Alerts trigger on any non-zero rate after the migration window.
- `backfill_completion_ratio` – gauge reporting per-lease completion.
- `seamless_schema_validation_failures_total` – counter for strict schema
  violations.

Recommended alert rules live in `alert_rules.yml` under the `seamless-*`
prefix. Wire them to PagerDuty (`service=Seamless`) and the `#seamless-ops`
Slack channel.

## Tracing and Logging

- **Tracing**: enable the `seamless.pipeline` span exporter. Spans contain
  `sla.phase`, `backfill.lease_id`, and `schema.validation_mode` attributes.
- **Logging**: configure `qmtl.logging.json` with `seamless.backfill` and
  `seamless.sla` channels at `INFO` level. The coordinator emits structured
  logs whenever it reclaims stale leases or skips invalid payloads.

## Runbooks

When an alert fires:

1. Open the Seamless SLA Overview dashboard and inspect the affected domain.
2. Use the Backfill Coordinator Health dashboard to confirm whether leases are
   stuck; reclaim via `scripts/lease_recover.py` if necessary.
3. Check tracing for anomalies in `seamless.pipeline` spans.
4. Escalate according to the ownership matrix in `operations/monitoring.md` and
   document the incident in the Seamless postmortem tracker.

{{ nav_links() }}
