---
title: "Backend Quickstart"
tags: [quickstart, gateway, dagmanager, worldservice]
author: "QMTL Team"
last_modified: 2025-09-23
---

{{ nav_links() }}

# Backend Quickstart (WS + GW + DM)

This quickstart brings up the core QMTL backend services for local development:

- WorldService (WS) – worlds, policies, decisions, activation
- Gateway (GW) – client-facing API, proxy to WS, ingest to DAG Manager
- DAG Manager (DM) – global DAG SSOT, diff, queue orchestration

See also: Docker usage and full stack notes in [Docker & Compose](docker.md) and
end-to-end tests in [E2E Testing](e2e_testing.md).

## Prerequisites

- Python environment managed by uv: `uv venv && uv pip install -e .[dev]`
- Optional: Docker/Compose for infra services

## Fast start: validate and launch

Follow this quick validation and launch loop when an operations YAML is ready:

1. **Static validation** – confirm the structure before booting services.

   ```bash
   uv run qmtl config validate --config <path-to-config> --offline
   ```

2. **Gateway** – start the public entrypoint with the validated config.

   ```bash
   qmtl service gateway --config <path-to-config>
   ```

3. **DAG Manager** – launch orchestration services with the same settings.

   ```bash
   qmtl service dagmanager server --config <path-to-config>
   ```

For long-lived processes, copy the file to `qmtl.yml` in the working directory so the
service commands auto-discover it.

## Option A — Run locally (no Docker)

1) Start WorldService (SQLite + Redis example)

```bash
cat > worldservice.yml <<'EOF'
worldservice:
  dsn: sqlite:///worlds.db
  redis: redis://localhost:6379/0
  bind:
    host: 0.0.0.0
    port: 8080
  auth:
    header: Authorization
    tokens: []
EOF
uv run uvicorn qmtl.services.worldservice.api:create_app --factory --host 0.0.0.0 --port 8080
```

Run the command from the same directory so `worldservice.yml` is discovered.

2) Configure and start Gateway

- Edit `qmtl/examples/qmtl.yml`:
  - `gateway.worldservice_url: http://localhost:8080`
  - `gateway.enable_worldservice_proxy: true`
  - `gateway.events.secret: <generate a 64-character hex secret>`
  - `gateway.websocket.rate_limit_per_sec: 0` (leave `0` for unlimited)
- Start Gateway with the config:

```bash
qmtl service gateway --config qmtl/examples/qmtl.yml
```

3) Start DAG Manager (same config)

```bash
qmtl service dagmanager server --config qmtl/examples/qmtl.yml
```

Notes
- For production-like topics, set Kafka/Neo4j in the YAML. Without them, DM uses in-memory repo and queues.
- Topic namespaces are on by default. For simple local testing without prefixes set `dagmanager.enable_topic_namespace: false` in the same YAML.

## Option B — Docker Compose

Use the E2E stack to run infra + services:

> Canonical Compose files live in the package under
> {{ code_link('qmtl/examples/templates/local_stack.example.yml', text='`qmtl/examples/templates/local_stack.example.yml`') }}
> and
> {{ code_link('qmtl/examples/templates/backend_stack.example.yml', text='`qmtl/examples/templates/backend_stack.example.yml`') }}.
> Copy one of those templates into your project when you need a baseline stack.

```bash
docker compose -f tests/docker-compose.e2e.yml up --build -d
# Gateway: http://localhost:8000, DAG Manager gRPC: 50051
```

Or the fuller root stack with health checks and volumes:

```bash
docker compose up -d
# Gateway: http://localhost:8000, DAG Manager HTTP: http://localhost:8001/health
```

Stop stacks with `docker compose down` (add `-v` to remove volumes).

## Verify

- Gateway status: `curl http://localhost:8000/status`
- DAG Manager HTTP health (root stack): `curl http://localhost:8001/health`
- Neo4j init (if using Neo4j):

```bash
qmtl service dagmanager neo4j-init \
  --uri bolt://localhost:7687 --user neo4j --password neo4j
```

## Try a Strategy (Gateway + WorldService)

Run a sample strategy against Gateway with a world id:

```bash
python -m qmtl.examples.general_strategy \
  --gateway-url http://localhost:8000 \
  --world-id demo
```

For offline runs (no WS/GW): `python -m qmtl.examples.general_strategy`.

## Troubleshooting

- Ports in use: ensure 8000 (GW), 50051/8001 (DM), 6379 (Redis), 7687/7474 (Neo4j), 9092 (Kafka) are free.
- WorldService proxy disabled: Gateway will still run; SDKs fall back to offline/backtest modes.
- Apple Silicon: add `platform: linux/amd64` to services that lack arm64 images.

{{ nav_links() }}

