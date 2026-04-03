---
title: "Gateway Runtime and Deployment Profiles"
tags: [operations, gateway, runtime]
author: "QMTL Team"
last_modified: 2026-04-03
---

{{ nav_links() }}

# Gateway Runtime and Deployment Profiles

## Related Documents

- [Gateway](../architecture/gateway.md)
- [Backend Quickstart](backend_quickstart.md)
- [Config CLI](config-cli.md)
- [ControlBus/Queue Standards](controlbus_queue_standards.md)
- [Risk Signal Hub Runbook](risk_signal_hub_runbook.md)

## Purpose

This document captures Gateway runtime requirements, preflight checks, and incident handling from an operator perspective.

- Normative API, compute-context, and proxy contracts live in [Gateway](../architecture/gateway.md).
- This page focuses on what must exist for Gateway to start cleanly, and how it should degrade or fail when dependencies are missing.

## Runtime Profiles

### `profile: dev`

- Allow an in-memory Redis shim when `gateway.redis_dsn` is empty.
- Disable the ControlBus consumer when `gateway.controlbus_brokers` or `gateway.controlbus_topics` are empty.
- Disable the Commit-Log writer/consumer when `gateway.commitlog_bootstrap` or `gateway.commitlog_topic` are empty.
- If the WorldService proxy is disabled or unreachable, the submit path must remain on the safe fallback path.

### `profile: prod`

- The following are fail-fast requirements.
  - `gateway.redis_dsn`
  - `gateway.database_backend=postgres` together with `gateway.database_dsn`
  - `gateway.controlbus_brokers`, `gateway.controlbus_topics`
  - `gateway.commitlog_bootstrap`, `gateway.commitlog_topic`
- If any required item is missing, both `qmtl config validate` and service boot should fail.
- Do not treat dev-style in-memory fallbacks as acceptable production operation.

## Preflight Checks

1. `uv run qmtl config validate --config <path> --offline`
2. Confirm `gateway.worldservice_url` and `gateway.enable_worldservice_proxy`
3. Confirm `gateway.events.secret`
4. In prod, verify connectivity to Redis, Postgres, ControlBus, and Commit-Log
5. If Risk Signal Hub is enabled, verify the `risk_hub` token, inline/offload thresholds, and blob-store settings

## External Dependencies

- **WorldService**: decision/activation/allocation proxy and world binding upsert boundary
- **Redis**: ingest/FSM/cache hot path
- **Postgres**: production persistence boundary
- **ControlBus**: activation/policy/queue fan-out input
- **Commit-Log**: durable ingest and relay traceability
- **Risk Signal Hub**: Gateway is producer-only; consumption belongs to WorldService and the exit engine

## Incident Checklist

- WorldService unreachable:
  - verify safe-mode downgrade rather than trusting live hints
  - inspect world-proxy and submit-postprocess logs
- Redis missing:
  - in prod, startup failure is expected
  - in dev, confirm whether Gateway unintentionally booted with in-memory fallback
- ControlBus lag or disabled consumer:
  - check activation/state relay staleness first
  - inspect topic and consumer-group health alongside [ControlBus/Queue Standards](controlbus_queue_standards.md)
- Commit-Log disabled or mismatched:
  - inspect `gateway.commitlog_*` settings and serialization warnings
- Risk Signal Hub push failures:
  - Gateway is the producer, so check retry/backoff behavior and hub-token failures first
  - follow [Risk Signal Hub Runbook](risk_signal_hub_runbook.md) for downstream handling

## Observability

- Service health: `/status`
- Gateway metrics and alerts are documented in [Monitoring and Alerting](monitoring.md).
- World-status and allocation-relay issues should be read together with [World Activation Runbook](activation.md) and [Rebalancing Execution Adapter](rebalancing_execution.md).

{{ nav_links() }}
