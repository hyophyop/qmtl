# Monitoring and Alerting

This document outlines sample Prometheus alerts and Grafana dashboards for QMTL services.

## Alert Rules

Prometheus can load `alert_rules.yml` to activate alerts for the DAG manager and gateway. Additional rules have been added for garbage collection. The file can be mounted into the Prometheus container via its configuration.

## Grafana Dashboards

Example Grafana dashboards are provided in `docs/dashboards/`. Import the JSON file into Grafana to visualise queue counts and garbage collector activity. The dashboard uses the `orphan_queue_total` metric exposed by the DAG manager.

## QuestDB Recorder Demo

The script `examples/questdb_parallel_example.py` runs two moving-average strategies in parallel while persisting every `StreamInput` payload to QuestDB. It starts the metrics server on port `8000` and prints aggregated Prometheus metrics when finished. Execute it as follows:

```bash
python examples/questdb_parallel_example.py
```

Monitor `http://localhost:8000/metrics` during execution or check the printed output. Key counters include `node_processed_total` for processed events and `event_recorder_errors_total` when the recorder fails to persist rows.

