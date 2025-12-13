# World Validation Observability (SLO/Dashboards/Alerts)

This document defines core SLIs/SLOs and dashboard/alert criteria so the WorldService-based World Validation layer can be trusted at operational scale.

## Scope

- Risk Signal Hub snapshot ingestion (HTTP push + ControlBus consumption)
- Extended validation worker runs (cohort/portfolio/stress/live)
- Live monitoring run (materialize stage=live EvaluationRun)
- EvaluationRun-backed `validation_health` / SR 11-7 invariant checks

## Draft SLI/SLOs

### 1) RiskHub Freshness

- SLI: `risk_hub_snapshot_lag_seconds{world_id}`
- Recommended SLO:
  - WARNING: `> 600s` (10m)
  - CRITICAL: `> 1800s` (30m)

### 2) Snapshot Processing Health (ControlBus Consumer)

- SLI:
  - Throughput: `rate(risk_hub_snapshot_processed_total[5m])`
  - Error ratio: `rate(risk_hub_snapshot_failed_total[5m]) / (rate(risk_hub_snapshot_processed_total[5m]) + rate(risk_hub_snapshot_failed_total[5m]))`
  - DLQ: `increase(risk_hub_snapshot_dlq_total[5m])`
  - Dedupe/TTL: `increase(risk_hub_snapshot_dedupe_total[5m])`, `increase(risk_hub_snapshot_expired_total[5m])`

### 3) Extended Validation Worker

- SLI:
  - Success/failure: `rate(extended_validation_run_total{status="success"}[5m])`, `rate(extended_validation_run_total{status=~"failure|enqueue_failed"}[5m])`
  - p95 latency: `histogram_quantile(0.95, sum(rate(extended_validation_run_latency_seconds_bucket[5m])) by (le, world_id, stage))`

### 4) Live Monitoring Materialization

- SLI:
  - Run success/failure: `rate(live_monitoring_run_total{status="success"}[5m])`, `rate(live_monitoring_run_total{status="failure"}[5m])`
  - Updated strategies: `increase(live_monitoring_run_updated_strategies_total[1h])`

### 5) Validation Health / Invariants

- EvaluationRun’s `metrics.diagnostics.validation_health.metric_coverage_ratio` is recorded in the **EvaluationRun storage layer**, not Prometheus.
- Recommended operational checks:
  - Invariant report: `GET /worlds/{world_id}/validations/invariants`
  - Sample the latest EvaluationRun and inspect `diagnostics.validation_health` (by world/stage)

## Alertmanager Rules (Example Snippet)

{% raw %}
```yaml
groups:
  - name: world_validation
    rules:
      - alert: RiskHubSnapshotLagHigh
        expr: risk_hub_snapshot_lag_seconds > 1800
        for: 10m
        labels:
          severity: critical
        annotations:
          summary: "RiskHub snapshot lag high"
          description: "world={{ $labels.world_id }} lag={{ $value }}s"

      - alert: RiskHubSnapshotDlqSpike
        expr: increase(risk_hub_snapshot_dlq_total[10m]) > 0
        for: 0m
        labels:
          severity: warning
        annotations:
          summary: "RiskHub DLQ spike"
          description: "world={{ $labels.world_id }} stage={{ $labels.stage }}"

      - alert: ExtendedValidationFailures
        expr: increase(extended_validation_run_total{status=~\"failure|enqueue_failed\"}[10m]) > 0
        for: 0m
        labels:
          severity: warning
        annotations:
          summary: "Extended validation failures"
          description: "world={{ $labels.world_id }} stage={{ $labels.stage }}"
```
{% endraw %}

## Dashboard (Recommended Panels)

- RiskHub freshness: `risk_hub_snapshot_lag_seconds` (by world_id)
- Snapshot pipeline health: processed/failed/retry/dlq/dedupe/expired
- Extended validation: success/failure, p95 latency
- Live monitoring: run success/failure, updated strategies
- Invariants/health: `/validations/invariants` results (recommended to collect periodically via an ops script/external poller)
