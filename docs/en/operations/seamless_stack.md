# Seamless Stack Templates

This runbook describes how to bootstrap a Seamless deployment using the
templates under `operations/`.

## Directory Overview

The repository ships the following artifacts:

- `operations/docker-compose.full.yml` – Full-stack Compose bundle including Gateway, DAG Manager, WorldService, Seamless coordinator, Redis, QuestDB, Postgres, Neo4j, Redpanda, and MinIO.
- `operations/docker-compose.dev.override.yml` – Dev override to run the full bundle with local/in-memory defaults.
- `operations/seamless/docker-compose.seamless.yml` – Standalone Seamless coordinator bundle (kept for partial stacks/samples).
- `operations/config/dev.full.yml`, `operations/config/prod.full.yml` – Ready-to-mount full-stack sample configs.
- Helm (planned): mirror the full-stack Compose structure when Kubernetes deployment is needed.
- `qmtl/examples/seamless/presets.yaml` – SLA and conformance presets aligned
  with the QMTL SDK defaults. A convenience copy remains under
  `operations/seamless/presets.yaml` for operators working from the repository
  checkout.
- `operations/seamless/README.md` – Detailed documentation of services and
  configuration options.
- `operations/config/*.yml` – Sample QMTL runtime configurations for
  development, staging, and production deployments.

The Compose bundle now ships sensible defaults, so no `.env` bootstrap is
required before launching the stack.

## Launching the Stack

### Full stack (prod default)

```bash
docker compose -f operations/docker-compose.full.yml up -d
```

Mount `operations/config/prod.full.yml` (after filling secrets/endpoints) for production-like deployments.

### Local/dev override

```bash
docker compose -f operations/docker-compose.full.yml -f operations/docker-compose.dev.override.yml up -d
```

This path uses local/in-memory defaults and `operations/config/dev.full.yml`. Coordinator may be optional in dev, but prod requires `seamless.coordinator_url` plus Redis/QuestDB/MinIO.

### Upgrade notes

- Legacy users of `operations/seamless/docker-compose.seamless.yml` should migrate to the full bundle for prod/stage to avoid stub fallback of the coordinator.
- Keep the standalone bundle only for partial/local demos; prod should mount `operations/config/prod.full.yml` into `docker-compose.full.yml`.
- Helm adoption is on the roadmap; use the full Compose bundle until the chart is published.

### Standalone coordinator sample (partial stack)

```bash
docker compose -f operations/seamless/docker-compose.seamless.yml up -d
```

Verify the services:

- Coordinator health probe – `curl http://localhost:8080/healthz`
- QuestDB UI – `http://localhost:9000`
- MinIO console – `http://localhost:9001`

Adjust `operations/config/*.yml` to point at your coordinator, select the
desired SLA/conformance presets, and configure artifact capture. These YAML
files replace the previous `.env` workflow and can be passed to the CLI via
`--config` or mounted into your deployment tooling.

## Using the Presets

Load the SLA and conformance presets by pointing `seamless.presets_file` at the
desired document and selecting `seamless.sla_preset` /
`seamless.conformance_preset`. Each entry under `sla_presets` maps to
`qmtl.runtime.sdk.sla.SLAPolicy`, and each entry under `conformance_presets`
defines whether Seamless should block responses when warnings occur. The default
pair is:

- `baseline` – strict deadlines that fail fast on SLA breaches.
- `strict-blocking` – blocks responses when conformance warnings are emitted and
  enforces a one-minute interval.

Use the `tolerant-partial` and `permissive-dev` presets for exploratory work or
backfill migrations that can tolerate partial fills.
