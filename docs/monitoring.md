# Monitoring and Alerting

This document outlines sample Prometheus alerts and Grafana dashboards for QMTL services.

## Alert Rules

Prometheus can load `alert_rules.yml` to activate alerts for the DAG manager and gateway. The repository ships a minimal example with a couple of core alerts. Mount the file into your Prometheus container and expand it as needed.

### Additional Alert Reference

The following alerts are available for inspiration when extending `alert_rules.yml`:

- **DiffDurationHigh** – triggers when `diff_duration_ms_p95` exceeds 200 ms.
- **NodeCacheMemoryHigh** – warns if `nodecache_resident_bytes` surpasses 5 GB.
- **QueueCreateErrors** – fires when `queue_create_error_total` increases.
- **SentinelGap** – indicates a missing diff sentinel via `sentinel_gap_count`.
- **OrphanQueuesGrowing** – detects rises in `orphan_queue_total` over a three-hour window.
- **GatewayLatencyHigh** – alerts when `gateway_e2e_latency_p95` exceeds 150 ms.
- **LostRequests** – reports lost diff submissions based on `lost_requests_total`.
- **GCSchedulerStall** – warns if `gc_last_run_timestamp` lags by more than ten minutes.

## Grafana Dashboards

Example Grafana dashboards are provided in `docs/dashboards/`. Import the JSON file into Grafana to visualise queue counts and garbage collector activity. The dashboard uses the `orphan_queue_total` metric exposed by the DAG manager.

## QuestDB Recorder Demo

The script `qmtl/examples/questdb_parallel_example.py` runs two moving-average strategies in parallel while persisting every `StreamInput` payload to QuestDB. It starts the metrics server on port `8000` and prints aggregated Prometheus metrics when finished. Execute it as follows:

```bash
python -m qmtl.examples.questdb_parallel_example
```

Monitor `http://localhost:8000/metrics` during execution or check the printed output. Key counters include `node_processed_total` for processed events and `event_recorder_errors_total` when the recorder fails to persist rows.

## Gateway & DAG Manager Metrics

Both services expose a Prometheus endpoint. Circuit breaker activity is tracked via gauges:

- `dagclient_breaker_open_total` — increments each time the Gateway's gRPC client trips open.
- `kafka_breaker_open_total` — increments each time the DAG manager's Kafka admin breaker opens.

Configuration options control the breakers:

```yaml
gateway:
  dagclient_breaker_threshold: 3  # failures before opening
dagmanager:
  kafka_breaker_threshold: 3
  neo4j_breaker_threshold: 3
```

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

