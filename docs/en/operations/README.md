---
title: "Operations"
tags:
  - operations
  - overview
author: "QMTL Team"
last_modified: 2026-04-03
---

{{ nav_links() }}

# Operations

Guidelines for running and maintaining QMTL in production.

## Starting Points

- [Backend Quickstart](backend_quickstart.md): Local WS/GW/DM bring-up and base smoke flow.
- [Deployment Path](deployment_path.md): Standard release deployment path.
- [Config CLI](config-cli.md): Preflight validation and operator startup order.

## Service Runtime

- [Gateway Runtime and Deployment Profiles](gateway_runtime.md): Gateway dependencies, fail-fast rules, and incident handling.
- [DAG Manager Runtime and Deployment Profiles](dag_manager_runtime.md): Neo4j/Kafka/ControlBus operating requirements.
- [ControlBus Runtime and Incident Handling](controlbus_operations.md): broker/topic, lag, and ACK/gap response.
- [Risk Signal Hub Runbook](risk_signal_hub_runbook.md): snapshot freshness, token, offload, and worker operations.

## Supplemental Runbooks

- [Fill Replay Runbook](fills_replay.md): current constraints around the non-public replay surface.
- [WS-only Resilience & Recovery](ws_resilience.md): reconnect and deduplication behavior for WebSocket-only paths.
- [Neo4j Schema Initialization](neo4j_migration.md): init-only command and index scope.

## Validation and Observability

- [E2E Testing](e2e_testing.md): End-to-end testing practice.
- [Monitoring](monitoring.md): Observability and metrics.
- [Core Loop Observability Minimum Set](observability_core_loop.md): minimum dashboard and SLO boundaries.
- [World Validation Observability](world_validation_observability.md): validation and promotion observability points.
- [Grafana Dashboard](dashboards/gc_dashboard.json): Sample metrics dashboard.

## Control-Plane and Approval Procedures

- [World Activation Runbook](activation.md): freeze/drain/switch/unfreeze procedure.
- [Rebalancing Execution Adapter](rebalancing_execution.md): order-conversion and execution boundary after plan/apply.
- [World Validation Governance](world_validation_governance.md): override and re-review procedure.
- [ControlBus/Queue Standards](controlbus_queue_standards.md): topic, consumer-group, and retry/DLQ rules.

## Release and Change Management

- [Canary Rollout](canary_rollout.md): gradual deployment strategy.
- [Risk Management](risk_management.md): operational risk controls.
- [Timing Controls](timing_controls.md): scheduling safeguards.

{{ nav_links() }}
