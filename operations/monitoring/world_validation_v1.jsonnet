{
  "bundle": "world_validation_observability",
  "version": 1,
  "dashboards": [
    {
      "uid": "world-validation-overview",
      "title": "World Validation Overview",
      "tags": ["world", "validation", "observability"],
      "panels": [
        {
          "type": "timeseries",
          "title": "RiskHub Snapshot Lag (seconds)",
          "description": "Freshness of the latest RiskHub snapshot per world.",
          "targets": [
            {
              "expr": "risk_hub_snapshot_lag_seconds",
              "legendFormat": "{{world_id}}"
            }
          ]
        },
        {
          "type": "timeseries",
          "title": "RiskHub Snapshot Processing (rate)",
          "description": "Processed vs failed snapshot events per world/stage.",
          "targets": [
            {
              "expr": "sum by (world_id, stage) (rate(risk_hub_snapshot_processed_total[5m]))",
              "legendFormat": "processed {{world_id}}/{{stage}}"
            },
            {
              "expr": "sum by (world_id, stage) (rate(risk_hub_snapshot_failed_total[5m]))",
              "legendFormat": "failed {{world_id}}/{{stage}}"
            }
          ]
        },
        {
          "type": "timeseries",
          "title": "RiskHub DLQ / Retry / Dedupe / Expired",
          "description": "Operational signals for snapshot ingestion.",
          "targets": [
            {
              "expr": "sum by (world_id, stage) (increase(risk_hub_snapshot_dlq_total[10m]))",
              "legendFormat": "dlq {{world_id}}/{{stage}}"
            },
            {
              "expr": "sum by (world_id, stage) (rate(risk_hub_snapshot_retry_total[5m]))",
              "legendFormat": "retry {{world_id}}/{{stage}}"
            },
            {
              "expr": "sum by (world_id, stage) (rate(risk_hub_snapshot_dedupe_total[5m]))",
              "legendFormat": "dedupe {{world_id}}/{{stage}}"
            },
            {
              "expr": "sum by (world_id, stage) (rate(risk_hub_snapshot_expired_total[5m]))",
              "legendFormat": "expired {{world_id}}/{{stage}}"
            }
          ]
        },
        {
          "type": "timeseries",
          "title": "RiskHub Snapshot Processing Latency (p95 seconds)",
          "description": "p95 time from snapshot creation to WS processing.",
          "targets": [
            {
              "expr": "histogram_quantile(0.95, sum by (le, world_id, stage) (rate(risk_hub_snapshot_processing_latency_seconds_bucket[5m])))",
              "legendFormat": "{{world_id}}/{{stage}}"
            }
          ]
        },
        {
          "type": "timeseries",
          "title": "Extended Validation Runs (rate)",
          "description": "Success/failure rate for extended validation workers.",
          "targets": [
            {
              "expr": "sum by (world_id, stage) (rate(extended_validation_run_total{status=\"success\"}[5m]))",
              "legendFormat": "success {{world_id}}/{{stage}}"
            },
            {
              "expr": "sum by (world_id, stage) (rate(extended_validation_run_total{status=~\"failure|enqueue_failed\"}[5m]))",
              "legendFormat": "failure {{world_id}}/{{stage}}"
            }
          ]
        },
        {
          "type": "timeseries",
          "title": "Extended Validation Latency (p95 seconds)",
          "description": "p95 latency of extended validation runs.",
          "targets": [
            {
              "expr": "histogram_quantile(0.95, sum by (le, world_id, stage) (rate(extended_validation_run_latency_seconds_bucket[5m])))",
              "legendFormat": "{{world_id}}/{{stage}}"
            }
          ]
        },
        {
          "type": "timeseries",
          "title": "Live Monitoring Runs (rate)",
          "description": "Success/failure rate for live monitoring materialization.",
          "targets": [
            {
              "expr": "sum by (world_id) (rate(live_monitoring_run_total{status=\"success\"}[5m]))",
              "legendFormat": "success {{world_id}}"
            },
            {
              "expr": "sum by (world_id) (rate(live_monitoring_run_total{status=\"failure\"}[5m]))",
              "legendFormat": "failure {{world_id}}"
            }
          ]
        },
        {
          "type": "timeseries",
          "title": "Live Monitoring Updated Strategies",
          "description": "Total number of strategies updated by LiveMonitoringWorker.",
          "targets": [
            {
              "expr": "sum by (world_id) (increase(live_monitoring_run_updated_strategies_total[1h]))",
              "legendFormat": "{{world_id}}"
            }
          ]
        }
      ]
    }
  ]
}

