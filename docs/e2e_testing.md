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

Start all services using Docker Compose:

```bash
docker compose -f tests/docker-compose.e2e.yml up -d
```

This launches Redis, Postgres, Neo4j, Kafka, Zookeeper and the `qmtl-gateway` and `qmtl-dagm` containers. The gateway exposes port `18000` and the DAG‑Manager gRPC endpoint is available on `15051`.

## Running the tests

Execute the end-to-end tests within the uv environment:

```bash
uv run -- pytest tests/e2e
```

To execute the entire test suite run:

```bash
uv run pytest -q tests
```

