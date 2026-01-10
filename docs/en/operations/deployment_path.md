---
title: "Deployment Path Decision (Release 0.1)"
tags: [deployment, release]
author: "QMTL Team"
last_modified: 2026-01-10
---

{{ nav_links() }}

# Deployment Path Decision (Release 0.1)

For Release 0.1, the **single official deployment path is Docker/Compose**. Wheel-based execution remains for development experiments only; documentation, templates, and smoke procedures are standardized on Compose.

## Decision summary

- **Chosen path:** Docker/Compose
- **Deployment artifacts:** `Dockerfile`, `docker-compose.yml`, `operations/docker-compose.qmtl.yml`
- **Not chosen:** direct wheel execution (not an official deployment procedure)

## Required infrastructure and ports

The Compose stack depends on the following infrastructure and default ports.

| Component | Purpose | Default ports | Compose service |
| --- | --- | --- | --- |
| Redis | Gateway cache/session | 6379 | `redis` |
| Postgres | Gateway persistence | 5432 | `postgres` |
| Neo4j | DAG Manager graph store | 7687/7474 | `neo4j` |
| Zookeeper | Kafka metadata | 2181 | `zookeeper` |
| Kafka | DAG queue/events | 9092 | `kafka` |
| Gateway | submit/status API | 8000 | `gateway` |
| DAG Manager | gRPC API | 50051 | `dagmanager` |

## Configuration and secrets

The baseline config is `operations/docker-compose.qmtl.yml`. Copy/override it for production.

Required settings (Release 0.1 Compose baseline):

- `gateway.redis_dsn`
- `gateway.database_backend=postgres`
- `gateway.database_dsn`
- `dagmanager.neo4j_dsn`
- `dagmanager.kafka_dsn`

Optional/extended settings (enable only when needed):

- `gateway.events.secret` (event signing)
- `gateway.commitlog_*`, `gateway.controlbus_*` (commit log/ControlBus integration)
- `worldservice.redis`, `worldservice.controlbus_*` (when adding WorldService)

Manage secrets via `.env` or a secret manager; do not commit plaintext values into Compose files.

## Deployment steps (Compose)

1) Boot the stack

```bash
docker compose up -d
```

2) Check status

```bash
docker compose ps
curl http://localhost:8000/status
```

3) Shut down

```bash
docker compose down
```

## Minimal smoke (health check + basic submit)

This procedure verifies “health + basic submit” in the smallest loop.

1) Gateway health check

```bash
curl http://localhost:8000/status
```

2) Basic submit (sample strategy, no QuestDB dependency)

```bash
python -m qmtl.examples.indicators_strategy \
  --gateway-url http://localhost:8000 \
  --world-id demo
```

## Related docs/templates

- [Backend Quickstart](backend_quickstart.md)
- [Docker & Compose](docker.md)
- Compose examples:
  - `docker-compose.yml`
  - `tests/docker-compose.e2e.yml`
  - `qmtl/examples/templates/local_stack.example.yml`
  - `qmtl/examples/templates/backend_stack.example.yml`

{{ nav_links() }}
