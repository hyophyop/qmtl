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

This launches Redis, Postgres, Neo4j, Kafka, Zookeeper and the `qmtl-gateway` and `qmtl-dagm` containers. The gateway exposes port `8000` and the DAG‑Manager gRPC endpoint is available on `50051`.

## Running the tests

Execute the end-to-end tests within the uv environment:

```bash
uv run -- pytest tests/e2e
```

To execute the entire test suite run:

```bash
uv run pytest -q tests
```

## Backfills

Start a backfill when executing a strategy to load historical data before
live processing begins:

```bash
python -m qmtl.sdk tests.sample_strategy:SampleStrategy \
       --mode backtest \
       --start-time 1700000000 \
       --end-time 1700003600
```

See [backfill.md](backfill.md) for a full overview of the workflow.

