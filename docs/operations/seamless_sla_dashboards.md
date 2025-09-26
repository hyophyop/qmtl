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
Grafana to provision the three core dashboards shipped with the repository:

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
  `ConformancePipeline` when normalisation warnings occur. Individual flag
  types appear in the dashboard's "Flag Breakdown" table, while aggregate
  warnings increment `seamless_conformance_warning_total`.
- Phase-specific latency histograms: `seamless_storage_wait_ms`,
  `seamless_backfill_wait_ms`, `seamless_live_wait_ms`, and
  `seamless_total_ms`. All four carry `{node_id, interval, world_id}` labels
  so that latency heatmaps can be filtered per domain.
- Coverage and freshness gauges: `coverage_ratio` and
  `live_staleness_seconds` expose the served vs requested range and the gap to
  the most recent bar. They share the `{node_id, interval, world_id}` label set
  and backstop the domain gate HOLD automation.
- Gap repair and coordinator health: `gap_repair_latency_ms` tracks the wall
  clock time to heal a missing window. `backfill_completion_ratio` remains the
  primary coordinator health gauge, now complemented by
  `seamless_rl_tokens_available` and `seamless_rl_dropped_total` for Redis
  token bucket headroom.
- Artifact observability: `artifact_publish_latency_ms`,
  `artifact_bytes_written`, and `fingerprint_collisions` make it trivial to
  wire burn-down panels for publishing lag, storage throughput, and duplicate
  fingerprints.
- Domain downgrade counters: `domain_gate_holds` and `partial_fill_returns`
  emit a reason-labelled counter every time the SLA policy downgrades a
  response. Use these to correlate alert storms with HOLD/PARTIAL_FILL surges.

Alert rules under the `seamless-*` prefix have been added to `alert_rules.yml`:

- `SeamlessSla99thDegraded` raises a warning when the 99th percentile of
  `seamless_sla_deadline_seconds` climbs above budget for five consecutive
  minutes.
- `SeamlessBackfillStuckLease` pages when `backfill_completion_ratio` stays
  below 50% for any lease.
- `SeamlessConformanceFlagSpike` notifies when a surge of conformance flags is
  observed over a 15-minute window.

Ensure PagerDuty and Slack routes are configured in environments where these
alerts should page. The alert annotations link back to this runbook.

## Validation Tooling

Two operational scripts now ship alongside the dashboards:

- `scripts/inject_sla_violation.py` emits synthetic SLA metrics, optionally
  writing the Prometheus exposition text to disk or serving it temporarily via
  HTTP. Use it to validate Grafana panels and alert rules without waiting for a
  live incident:

  ```bash
  uv run scripts/inject_sla_violation.py seam-node-1 --duration 240 --repetitions 5 --write-to /tmp/seamless.metrics
  ```

- `scripts/lease_recover.py` releases stuck coordinator leases by failing or
  completing them explicitly. Provide `KEY:TOKEN` pairs exported from the
  coordinator's inspection endpoint. Example:

  ```bash
  uv run scripts/lease_recover.py --coordinator-url https://coordinator/v1 lease-A:deadbeef lease-B:feedface
  ```

Both scripts include `--dry-run` or `--serve` modes to simplify verification in
non-production environments.

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
