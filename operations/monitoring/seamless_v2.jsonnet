{
  "bundle": "seamless_v2_observability",
  "version": 1,
  "dashboards": [
    {
      "uid": "seamless-sla-overview",
      "title": "Seamless SLA Overview",
      "tags": ["seamless", "sla"],
      "panels": [
        {
          "type": "timeseries",
          "title": "99th Percentile Deadline (Total)",
          "description": "Tracks the p99 of seamless_sla_deadline_seconds across all phases.",
          "targets": [
            {
              "expr": "histogram_quantile(0.99, sum by (le) (rate(seamless_sla_deadline_seconds_bucket{phase=\"total\"}[5m])))",
              "legendFormat": "total"
            }
          ]
        },
        {
          "type": "timeseries",
          "title": "Phase Breakdown",
          "description": "Latency percentiles split by SLA phase.",
          "targets": [
            {
              "expr": "histogram_quantile(0.99, sum by (le, phase) (rate(seamless_sla_deadline_seconds_bucket[5m])))",
              "legendFormat": "{{phase}}"
            }
          ]
        },
        {
          "type": "stat",
          "title": "Current Total p95",
          "description": "Displays the most recent 95th percentile of the total SLA histogram.",
          "targets": [
            {
              "expr": "histogram_quantile(0.95, sum by (le) (rate(seamless_sla_deadline_seconds_bucket{phase=\"total\"}[5m])))"
            }
          ]
        }
      ]
    },
    {
      "uid": "seamless-backfill-health",
      "title": "Backfill Coordinator Health",
      "tags": ["seamless", "backfill"],
      "panels": [
        {
          "type": "stat",
          "title": "Active Leases",
          "targets": [
            {
              "expr": "sum(backfill_jobs_in_progress)"
            }
          ]
        },
        {
          "type": "timeseries",
          "title": "Completion Ratio by Lease",
          "targets": [
            {
              "expr": "avg by (lease_key) (backfill_completion_ratio)",
              "legendFormat": "{{lease_key}}"
            }
          ]
        },
        {
          "type": "table",
          "title": "Recent Coordinator Updates",
          "targets": [
            {
              "expr": "topk(10, backfill_last_timestamp)",
              "legendFormat": "{{node_id}}"
            }
          ]
        }
      ]
    },
    {
      "uid": "seamless-conformance-quality",
      "title": "Conformance Quality",
      "tags": ["seamless", "quality"],
      "panels": [
        {
          "type": "stat",
          "title": "Total Flags (15m)",
          "targets": [
            {
              "expr": "sum(increase(seamless_conformance_flag_total[15m]))",
              "legendFormat": "flags"
            }
          ]
        },
        {
          "type": "timeseries",
          "title": "Flags by Node",
          "targets": [
            {
              "expr": "sum by (node_id) (increase(seamless_conformance_flag_total[5m]))",
              "legendFormat": "{{node_id}}"
            }
          ]
        },
        {
          "type": "table",
          "title": "Flag Breakdown",
          "targets": [
            {
              "expr": "sum by (flag_type) (increase(seamless_conformance_flag_total[1h]))",
              "legendFormat": "{{flag_type}}"
            }
          ]
        }
      ]
    }
  ],
  "recordingRules": [
    {
      "name": "seamless_sla_total_p99_seconds",
      "expr": "histogram_quantile(0.99, sum by (le) (rate(seamless_sla_deadline_seconds_bucket{phase=\"total\"}[5m])))",
      "labels": {
        "component": "seamless"
      }
    }
  ]
}
