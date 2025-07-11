# Monitoring and Alerting

This document outlines sample Prometheus alerts and Grafana dashboards for QMTL services.

## Alert Rules

Prometheus can load `alert_rules.yml` to activate alerts for the DAG manager and gateway. Additional rules have been added for garbage collection. The file can be mounted into the Prometheus container via its configuration.

## Grafana Dashboards

Example Grafana dashboards are provided in `docs/dashboards/`. Import the JSON file into Grafana to visualise queue counts and garbage collector activity. The dashboard uses the `orphan_queue_total` metric exposed by the DAG manager.

## QuestDB Recorder Demo

The script `qmtl/examples/questdb_parallel_example.py` runs two moving-average strategies in parallel while persisting every `StreamInput` payload to QuestDB. It starts the metrics server on port `8000` and prints aggregated Prometheus metrics when finished. Execute it as follows:

```bash
python -m qmtl.examples.questdb_parallel_example
```

Monitor `http://localhost:8000/metrics` during execution or check the printed output. Key counters include `node_processed_total` for processed events and `event_recorder_errors_total` when the recorder fails to persist rows.

## SDK Metrics

The SDK's cache layer provides a small set of Prometheus metrics. Any service can
expose these by calling `metrics.start_metrics_server()`.

### Metric reference

| Name | Type | Description | Labels |
| ---- | ---- | ----------- | ------ |
| `cache_read_total` | Counter | Total number of cache reads grouped by upstream and interval | `upstream_id`, `interval` |
| `cache_last_read_timestamp` | Gauge | Unix timestamp of the most recent cache read | `upstream_id`, `interval` |
| `backfill_last_timestamp` | Gauge | Latest timestamp successfully backfilled | `node_id`, `interval` |
| `backfill_jobs_in_progress` | Gauge | Number of active backfill jobs | *(none)* |
| `backfill_failure_total` | Counter | Total number of backfill jobs that ultimately failed | `node_id`, `interval` |
| `backfill_retry_total` | Counter | Total number of backfill retry attempts | `node_id`, `interval` |

Start the server as part of your application:

```python
from qmtl.sdk import metrics

metrics.start_metrics_server(port=8000)
```

Metrics will then be available at `http://localhost:8000/metrics`.

