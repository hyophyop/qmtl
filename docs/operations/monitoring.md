---
title: "Monitoring and Alerting"
tags: []
author: "QMTL Team"
last_modified: 2025-08-25
---

{{ nav_links() }}

# Monitoring and Alerting

This document outlines sample Prometheus alerts and Grafana dashboards for QMTL services.

## Alert Rules

Prometheus can load `alert_rules.yml` to activate alerts for the DAG Manager and gateway. The repository ships a minimal example with a couple of core alerts. Mount the file into your Prometheus container and expand it as needed.

### Additional Alert Reference

The following alerts are available for inspiration when extending `alert_rules.yml`:

- **DiffDurationHigh** – triggers when `diff_duration_ms_p95` exceeds 200 ms.
- **DiffFailureRateHigh** – fires when `diff_failures_total` over `diff_requests_total` exceeds 5% (5m rate).
- **DiffThroughputLow** – warns when `diff_requests_total` 5m rate drops below 0.6/min.
- **NodeCacheMemoryHigh** – warns if total `nodecache_resident_bytes` (scope="total") exceeds 5 GB.
- **QueueCreateErrors** – fires when `queue_create_error_total` increases.
- **SentinelGap** – indicates a missing diff sentinel via `sentinel_gap_count`.
- **OrphanQueuesGrowing** – detects rises in `orphan_queue_total` over a three-hour window.
- **QueueLagHigh** – triggers when `queue_lag_seconds` exceeds `queue_lag_threshold_seconds` for a topic.
- **GatewayLatencyHigh** – alerts when `gateway_e2e_latency_p95` exceeds 150 ms.
- **LostRequests** – reports lost diff submissions based on `lost_requests_total`.
- **GCSchedulerStall** – warns if `gc_last_run_timestamp` lags by more than ten minutes.
- **NodeSlowProcessing** – triggers when `node_process_duration_ms` p95 exceeds 500 ms for a node.
- **NodeFailures** – fires when `node_process_failure_total` increases.
- **CrossContextCacheHit** – CRIT when `cross_context_cache_hit_total` > 0; the metric has an SLO of 0 and signals domain mixing. Follow the runbook below before resuming promotions.

## Grafana Dashboards

Example Grafana dashboards are provided in `dashboards/`. Import the JSON file into Grafana to visualise queue counts and garbage collector activity. The dashboard uses the `orphan_queue_total` metric exposed by the DAG Manager.

## QuestDB Recorder Demo

The script `qmtl/examples/questdb_parallel_example.py` runs two moving-average strategies in parallel while persisting every `StreamInput` payload to QuestDB. It starts the metrics server on port `8000` and prints aggregated Prometheus metrics when finished. Execute it as follows:

```bash
python -m qmtl.examples.questdb_parallel_example
```

Monitor `http://localhost:8000/metrics` during execution or check the printed output. Key counters include `node_processed_total` for processed events, `node_process_failure_total` for compute errors and `event_recorder_errors_total` when the recorder fails to persist rows.

## Gateway & DAG Manager Metrics

Both services expose a Prometheus endpoint. Start the DAG Manager metrics server with `qmtl service dagmanager metrics` (use `--port` to change the default 8000).
Circuit breaker activity is tracked via gauges:

- `dagclient_breaker_open_total` — increments each time the Gateway's gRPC client trips open.
- `kafka_breaker_open_total` — increments each time the DAG Manager's Kafka admin breaker opens.

Both breakers open after three consecutive failures and are not configurable.
The DAG Manager's Neo4j breaker also uses a fixed threshold of 3.

Kafka consumer lag per topic is exported via `queue_lag_seconds{topic}` along with `queue_lag_threshold_seconds{topic}` to express the configured alert boundary.

For DAG diff processing, the following counters standardize naming and enable SLA-based alerting:

- `diff_requests_total` — total diff requests processed (throughput baseline).
- `diff_failures_total` — total failed diff requests (for failure rate calculation).
- `cross_context_cache_hit_total` — MUST remain 0; any increment blocks promotions until the offending component is reset. Labels include `node_id`, `world_id`, `execution_domain`, `as_of`, and `partition`. Empty or unknown contexts are normalized to `__unset__` to ease alert routing.

### Runbook: Cross-context cache hits (SLO = 0)

1. **Acknowledge the alert.** Verify that `cross_context_cache_hit_total` has increased above zero. Record the label set attached to the increment for debugging.
2. **Freeze promotions.** Halt release workflows that touch the affected DAG version. Automated tooling should already block promotions while the counter is non-zero.
3. **Trace the offending context.** Compare the label set `(node_id, world_id, execution_domain, as_of, partition)` against recent deploys. Look for:
   - Backtests or dry-runs that reused live cache entries.
   - Missing `as_of` values (`__unset__` label) that caused compute-key fallback.
   - Partitioning changes (e.g., moved tenants) without cache invalidation.
4. **Purge the polluted cache.** Flush SDK node caches for the offending node or trigger a DAG Manager recompute with the correct context. Ensure ComputeKey isolation is re-established.
5. **Reset the counter.** After remediation, restart the component or invoke the cache reset tooling to clear the metric. Confirm the counter returns to zero for at least 10 minutes before resuming promotions.

Suggested Prometheus rules combine these into three core alert groups: latency (`diff_duration_ms_p95`), failure-rate (`rate(diff_failures_total)/rate(diff_requests_total)`), and throughput (`rate(diff_requests_total)`). See `alert_rules.yml` for working examples.

Unlike time-based breakers, QMTL requires an explicit success signal to
close a tripped breaker. Calls that verify remote health should inspect
their return value and invoke `reset()` when appropriate:

```python
if await client.status():
    client.breaker.reset()
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
| `node_processed_total` | Counter | Total number of node compute executions | `node_id` |
| `node_process_duration_ms` | Histogram | Duration of node compute execution in milliseconds | `node_id` |
| `node_process_failure_total` | Counter | Total number of node compute failures | `node_id` |
| `cross_context_cache_hit_total` | Counter | Number of cache hits where context (world/domain/as_of/partition) mismatched | `node_id`, `world_id`, `execution_domain`, `as_of`, `partition` (missing values emitted as `__unset__`) |

Start the server as part of your application:

```python
from qmtl.runtime.sdk import metrics

metrics.start_metrics_server(port=8000)
```

Metrics will then be available at `http://localhost:8000/metrics`.

## Tracing

QMTL emits OpenTelemetry spans for the Gateway, DAG Manager and SDK. Traces can
be exported to any OTLP-compatible backend such as Jaeger or Tempo.

### Configuration

Set the ``QMTL_OTEL_EXPORTER_ENDPOINT`` environment variable to the OTLP HTTP
collector endpoint before starting services:

```bash
export QMTL_OTEL_EXPORTER_ENDPOINT="http://localhost:4318/v1/traces"
```

When unset, spans are logged to the console which is useful for development.

### Sample Jaeger query

After running a strategy, view traces in Jaeger by filtering for the service
name:

```txt
service="gateway"
```

Selecting a trace shows the relationship between the SDK's HTTP request, the
Gateway submission and downstream gRPC calls to the DAG Manager.


{{ nav_links() }}
