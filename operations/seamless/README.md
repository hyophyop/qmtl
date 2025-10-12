# Seamless Stack Templates

The files in this directory provide a starting point for running the Seamless data
provider locally or in a staging environment. They package the core dependencies
(backfill coordinator, QuestDB history store, Redis rate limiter, and MinIO
artifact bucket) together with opinionated SLA and conformance presets.

## Contents

| File | Purpose |
| --- | --- |
| `docker-compose.seamless.yml` | Compose bundle for the coordinator, QuestDB, Redis, and MinIO services. |
| `presets.yaml` | Reference SLA and conformance presets that align with the provider defaults. Packaged copy lives in `qmtl/examples/seamless/presets.yaml`. |
| `../config/*.yml` | Sample QMTL runtime configurations for dev/stage/prod deployments. Point the SDK at these YAML files instead of exporting `.env` variables. |

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
  DSN (`redis://redis:6379/3`) is baked into the Compose file and can be
  overridden with environment variables when needed.

### `minio`

- Acts as an S3-compatible bucket for Seamless artifacts, regression reports,
  and conformance outputs. Override the bucket or credentials by exporting
  `MINIO_BUCKET`, `MINIO_ROOT_USER`, or `MINIO_ROOT_PASSWORD` before running
  Compose. Defaults are provided inline in the bundle for local testing.

## Runtime Configuration

Edit `operations/config/*.yml` to align the runtime with your deployment. These
YAML documents replace the previous `.env` workflow and can be mounted or
passed directly to the CLI via `--config`. The `seamless` section controls
coordinator access, artifact capture, and preset selection:

| Key | Description | Example |
| --- | --- | --- |
| `seamless.coordinator_url` | Base URL for the distributed coordinator used by SDK workers. | `http://seamless-coordinator:8080` |
| `seamless.artifacts_enabled` | Persist normalized frames to the filesystem for audits. | `true` |
| `seamless.artifact_dir` | Filesystem directory that stores captured artifacts. | `/var/lib/qmtl/seamless-artifacts` |
| `seamless.publish_fingerprint` | Whether to emit dataset fingerprints for governance pipelines. | `true` |
| `seamless.sla_preset` | Name of the SLA policy to load from `presets.yaml`. | `baseline` |
| `seamless.conformance_preset` | Conformance configuration key within `presets.yaml`. | `strict-blocking` |
| `seamless.presets_file` | Path (relative to the config file) to the presets document. | `../seamless/presets.yaml` |

Compose now injects coordinator and MinIO defaults directly, so no `.env`
bootstrap step is required. Override any setting by exporting the matching
environment variable before invoking `docker compose`.

## SLA and Conformance Presets

`operations/seamless/presets.yaml` defines reusable targets for
`qmtl.runtime.sdk.sla.SLAPolicy` and the conformance pipeline. Point
`seamless.presets_file` at the document and select the desired entries via
`seamless.sla_preset` and `seamless.conformance_preset` in your runtime config.

## Launching the Stack

1. Start the services:

   ```bash
   docker compose -f operations/seamless/docker-compose.seamless.yml up -d
   ```

2. Verify health:
   - Coordinator health: `curl http://localhost:8080/healthz`
   - QuestDB UI: `http://localhost:9000`
   - MinIO console: `http://localhost:${MINIO_CONSOLE_PORT}`

3. Configure your QMTL runtime by pointing the SDK at one of the
   `operations/config/*.yml` samples or a customised copy:

   ```bash
   uv run qmtl service gateway --config operations/config/dev.yml
   ```

   Update the selected YAML file to reference your coordinator URL,
   credentials, and desired presets.
