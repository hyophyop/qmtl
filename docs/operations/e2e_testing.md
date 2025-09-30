---
title: "End-to-End Testing"
tags: []
author: "QMTL Team"
last_modified: 2025-08-21
---

{{ nav_links() }}

# End-to-End Testing

This guide explains how to spin up the required services and execute the end-to-end test suite.

## Prerequisites

Make sure the following tools are installed and available on your `PATH`:

- `docker`
- `uv`

## Installing dependencies

Create the uv environment and install all development requirements:

```bash
uv venv
uv pip install -e .[dev]
```

## Bringing up the stack

Start all services using Docker Compose. Both the DAG Manager and Gateway
services build from the repository's top-level `Dockerfile`, which installs
QMTL via `uv pip install .` and mounts the project source so the `qmtl`
entrypoint is available:

```bash
docker compose -f tests/docker-compose.e2e.yml up --build -d
```

This launches Redis, Postgres, Neo4j, Kafka, Zookeeper and the `qmtl service gateway` and
`qmtl service dagmanager server` containers. The gateway exposes port `8000` and the DAG
Manager gRPC endpoint is available on `50051`.

## Running the tests

Execute the end-to-end tests within the uv environment:

```bash
uv run -m pytest -n auto tests/e2e
```

To specifically validate WorldService-first wiring and event subscription,
run the smoke test added under `tests/e2e/test_worldservice_smoke.py`:

```bash
uv run -m pytest -n auto tests/e2e/test_worldservice_smoke.py -q
```

The test performs:

- Health check against the Gateway `/status` endpoint
- Token issuance via `/events/subscribe` for two distinct `world_id`s and JWT claim check
- WebSocket handshake to `/ws/evt` for both tokens
- Strategy submissions per-world using the Gateway proxy

It does not require ControlBus or a running WorldService.

To execute the entire test suite run:

```bash
uv run -m pytest -n auto -q tests

Note: Parallel execution requires `pytest-xdist`. If not installed, add it with
`uv pip install pytest-xdist` or include it in your dev extras.
```

## Backfills

Start a backfill when executing a strategy to load historical data before
live processing begins:

```bash
qmtl tools sdk run tests.sample_strategy:SampleStrategy \
       --start-time 1700000000 \
       --end-time 1700003600
```

See [backfill.md](backfill.md) for a full overview of the workflow.


{{ nav_links() }}
