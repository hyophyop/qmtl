---
title: "Docker & Compose"
tags: [docker, compose]
author: "QMTL Team"
last_modified: 2025-09-04
---

{{ nav_links() }}

# Docker & Compose

This page explains how Docker is used in QMTL, what Compose files exist, and how to bring services up for local development and testing.

## Overview

- Docker is used to provision local infrastructure (Redis, Postgres, Neo4j, Zookeeper, Kafka) and to run QMTL services (Gateway, DAG Manager) in containers.
- Multiple Compose files serve different purposes: quick smoke checks, end-to-end (E2E) testing, and a fuller local stack for development.
- The repository also contains a top-level `Dockerfile` used by service containers during Compose builds.

## Compose Files

### Root stack: `docker-compose.yml`

- Purpose: Developer-focused, fuller local stack with infra + QMTL services.
- Services: `redis`, `postgres`, `neo4j`, `zookeeper`, `kafka`, `dag-manager`, `gateway`.
- Builds: `dag-manager` and `gateway` build from the top-level `Dockerfile`.
- Health checks: Most services expose simple health checks for faster feedback.
- Example:

```bash
docker compose up -d
docker compose ps
docker compose logs -f gateway
docker compose down
```

Notes:
- Ports: 8000 (Gateway), 50051/8001 (DAG Manager), 5432 (Postgres), 7687/7474 (Neo4j), 9092 (Kafka), 2181 (Zookeeper), 6379 (Redis).
- Volumes: Named volumes are used for persistence (e.g., `postgres_data`, `neo4j_data`).

### Minimal test stack: `tests/docker-compose.yml`

- Purpose: Fast smoke test to ensure Docker and basic networking work in CI/local.
- Services: `zookeeper`, `kafka` (pinned to `confluentinc` images), and a placeholder `gateway` using `python:3.11-slim` serving HTTP.
- Used by: `tests/test_docker_compose.py` which brings the stack up and then down.
- Example:

```bash
docker compose -f tests/docker-compose.yml up -d
docker compose -f tests/docker-compose.yml down
```

### E2E stack: `tests/docker-compose.e2e.yml`

- Purpose: Runs the end-to-end test suite against real infra and QMTL services.
- Services: `redis`, `postgres`, `neo4j`, `zookeeper`, `kafka`, plus QMTL `gateway` and `dagmanager` built from the repo `Dockerfile`.
- Used by: E2E docs and tests (see below). Validated by `tests/test_docker_compose_e2e.py`.
- Example:

```bash
docker compose -f tests/docker-compose.e2e.yml up --build -d
uv run -m pytest -n auto tests/e2e
docker compose -f tests/docker-compose.e2e.yml down
```

See also: [E2E Testing](e2e_testing.md)

## Dockerfile

Path: `Dockerfile`

- Base: `python:3.11-slim`
- Installs: `uv` and the QMTL package via `uv pip install .`
- Used by: Service builds in `docker-compose.yml` and `tests/docker-compose.e2e.yml`.

Quick build example (if you want an image outside of Compose):

```bash
docker build -t qmtl:dev .
```

## Common Commands

- Up/Down: `docker compose up -d` / `docker compose down`
- Inspect: `docker compose ps`, `docker compose logs -f <service>`
- Rebuild: `docker compose build --no-cache`
- Pull: `docker compose pull` (useful in CI for faster start)
- Project isolation: set `COMPOSE_PROJECT_NAME=qmtl` to avoid name collisions

## Troubleshooting

- Port conflicts: Ensure these ports are free locally: 8000, 50051, 5432, 7687, 7474, 9092, 2181, 6379.
- Kafka connectivity:
  - Minimal test stack advertises `PLAINTEXT://localhost:9092` for convenience.
  - Root stack advertises `kafka:9092` for in-network container connectivity.
- Stale volumes: Remove with `docker compose down -v` or `docker volume rm <name>`.
- Apple Silicon: If images lack `arm64`, set `platform: linux/amd64` for affected services (slower via emulation).
- Compose v2: Use `docker compose` (not the deprecated `docker-compose`).

## Where Docker is Referenced

- Compose files:
  - `docker-compose.yml` (root)
  - `tests/docker-compose.yml`
  - `tests/docker-compose.e2e.yml`
- Tests:
  - `tests/test_docker_compose.py` (skips if `docker` not installed)
  - `tests/test_docker_compose_e2e.py` (validates expected services present)
- Docs and README:
  - `README.md` (E2E quickstart)
  - `docs/operations/e2e_testing.md`
  - `docs/architecture/dag-manager.md` (integration note)

## Related

- [E2E Testing](e2e_testing.md)
- [DAG Manager](../architecture/dag-manager.md)

{{ nav_links() }}
