# Monitoring and Alerting

This document outlines sample Prometheus alerts and Grafana dashboards for QMTL services.

## Alert Rules

Prometheus can load `alert_rules.yml` to activate alerts for the DAG manager and gateway. Additional rules have been added for garbage collection. The file can be mounted into the Prometheus container via its configuration.

## Grafana Dashboards

Example Grafana dashboards are provided in `docs/dashboards/`. Import the JSON file into Grafana to visualise queue counts and garbage collector activity. The dashboard uses the `orphan_queue_total` metric exposed by the DAG manager.

