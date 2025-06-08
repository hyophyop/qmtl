# End-to-End Testing

This compose file spins up all required services for running the gateway and DAG-Manager together.

## Usage

```bash
docker compose -f tests/docker-compose.e2e.yml up -d
```

Services include Redis, Postgres, Neo4j, Kafka, Zookeeper and containers running the `qmtl-gateway` and `qmtl-dagm` CLIs.  The gateway exposes port `8000` and the DAG-Manager gRPC endpoint is available on `50051`.

