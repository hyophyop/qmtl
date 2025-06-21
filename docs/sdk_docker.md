# SDK Docker Environment

This guide explains how to start the Gateway and DAG Manager with their required services using Docker Compose. It provides a quick setup for testing strategies with the SDK.

## Requirements

- `docker`
- `uv` for installing dependencies

## Starting the stack

Launch all services with Docker Compose:

```bash
docker compose -f docker-compose.sdk.yml up -d
```

The compose file starts Neo4j, Postgres, Redis, Zookeeper, Kafka and runs the `qmtl-gateway` and `qmtl-dagm` containers. The Gateway listens on port `8000` while the DAG Manager gRPC endpoint is exposed on `50051`.

Stop the stack when finished:

```bash
docker compose -f docker-compose.sdk.yml down
```

## Running a sample strategy

After the stack is running, install dependencies and execute a strategy:

```bash
uv venv
uv pip install -e .[dev]
python -m qmtl.sdk tests.sample_strategy:SampleStrategy \
    --mode backtest \
    --start-time 2024-01-01 \
    --end-time 2024-02-01 \
    --gateway-url http://localhost:8000
```

For additional details on the SDK and strategy implementation, see [sdk_tutorial.md](sdk_tutorial.md).
