# Seamless Stack Templates

The files in this directory provide a starting point for running the Seamless data
provider locally or in a staging environment. They package the core dependencies
(backfill coordinator, QuestDB history store, Redis rate limiter, and MinIO
artifact bucket) together with opinionated SLA and conformance presets.

## Contents

| File | Purpose |
| --- | --- |
| `.env.example` | Seed environment variables that the Seamless runtime and Compose stack expect. Copy it to `.env` before launching containers. |
| `.gitignore` | Prevents accidental commits of local `.env` overrides. |
| `docker-compose.seamless.yml` | Compose bundle for the coordinator, QuestDB, Redis, and MinIO services. |
| `presets.yaml` | Reference SLA and conformance presets that align with the provider defaults. Packaged copy lives in `qmtl/examples/seamless/presets.yaml`. |

> **Note:** The packaged copy is distributed with the `qmtl.examples`
> module so SDK consumers can load presets without checking out the operations
> assets.

## Services

### `seamless-coordinator`

- Provides distributed backfill leases and exposes health/metrics endpoints on
  ports `8080` and `${SEAMLESS_COORDINATOR_PROMETHEUS_PORT}`.
- Consumes Redis for lease bookkeeping, QuestDB for historical coverage, and
  MinIO for artifact storage.
- Loads Seamless settings from `operations/config/*.yml`, including coordinator
  endpoints, artifact publishing, and preset selection.

### `questdb`

- Stores historical bars and backfill artifacts consumed by
  `QuestDBHistoryProvider` and `EnhancedQuestDBProvider`.
- Credentials are surfaced through the `QUESTDB_POSTGRES_*` variables and are
  referenced by both the coordinator and the Seamless SDK.

### `redis`

- Powers rate limiting and distributed locks for the coordinator. The default
  DSN (`redis://redis:6379/3`) is wired into the `.env.example` file.

### `minio`

- Acts as an S3-compatible bucket for Seamless artifacts, regression reports,
  and conformance outputs. The bucket name is configurable through
  `MINIO_BUCKET`.

## Runtime Configuration

Edit `operations/config/*.yml` to align the runtime with your deployment. The
`seamless` section controls coordinator access, artifact capture, and preset
selection:

| Key | Description | Example |
| --- | --- | --- |
| `seamless.coordinator_url` | Base URL for the distributed coordinator used by SDK workers. | `http://seamless-coordinator:8080` |
| `seamless.artifacts_enabled` | Persist normalized frames to the filesystem for audits. | `true` |
| `seamless.artifact_dir` | Filesystem directory that stores captured artifacts. | `/var/lib/qmtl/seamless-artifacts` |
| `seamless.publish_fingerprint` | Whether to emit dataset fingerprints for governance pipelines. | `true` |
| `seamless.sla_preset` | Name of the SLA policy to load from `presets.yaml`. | `baseline` |
| `seamless.conformance_preset` | Conformance configuration key within `presets.yaml`. | `strict-blocking` |
| `seamless.presets_file` | Path (relative to the config file) to the presets document. | `../seamless/presets.yaml` |

The coordinator service continues to honour its `.env` file for service-level
settings such as Redis DSNs and QuestDB credentials. Refer to
`docker-compose.seamless.yml` for the environment variables consumed by the
coordinator container.

## SLA and Conformance Presets

`operations/seamless/presets.yaml` defines reusable targets for
`qmtl.runtime.sdk.sla.SLAPolicy` and the conformance pipeline. Point
`seamless.presets_file` at the document and select the desired entries via
`seamless.sla_preset` and `seamless.conformance_preset` in your runtime config.

## Launching the Stack

1. Copy `.env.example` to `.env` and override secrets as needed.
2. Start the services:

   ```bash
   docker compose -f operations/seamless/docker-compose.seamless.yml up -d
   ```

3. Verify health:
   - Coordinator health: `curl http://localhost:8080/healthz`
   - QuestDB UI: `http://localhost:9000`
   - MinIO console: `http://localhost:${MINIO_CONSOLE_PORT}`

4. Update your unified configuration so runtime services match the stack, for
   example:

   ```yaml
   seamless:
     coordinator_url: http://localhost:8080

   connectors:
     seamless_worker_id: worker-a
   ```

   Validate with `uv run qmtl config validate --config path/to/qmtl.yml` before
   deploying.
