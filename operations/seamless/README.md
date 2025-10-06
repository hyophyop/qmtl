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
- Reads the `QMTL_SEAMLESS_*` variables to instruct the SDK where to find the
  coordinator and which presets to load.

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

## Environment Variables

Copy `.env.example` to `.env` and adjust the values as needed:

| Variable | Description | Default |
| --- | --- | --- |
| `QMTL_SEAMLESS_COORDINATOR_URL` | Base URL that the SDK uses to discover the coordinator. | `http://seamless-coordinator:8080` |
| `QMTL_SEAMLESS_ARTIFACTS` | When set to `1`, preserves normalized frames on disk for audits. | `1` |
| `QMTL_SEAMLESS_ARTIFACT_DIR` | Filesystem path that stores captured artifacts. | `/var/lib/qmtl/seamless-artifacts` |
| `QMTL_SEAMLESS_FP_MODE` | Fingerprint policy (`canonical`, `preview`, etc.). | `canonical` |
| `QMTL_SEAMLESS_PUBLISH_FP` | Whether to publish fingerprints to governance pipelines. | `true` |
| `QMTL_SEAMLESS_PREVIEW_FP` | Permit preview fingerprints to bypass governance. | `false` |
| `QMTL_SEAMLESS_EARLY_FP` | Allow early fingerprint publication before validation. | `false` |
| `QMTL_SEAMLESS_SLA_PRESET` | Key within `presets.yaml` to load an SLA policy. | `baseline` |
| `QMTL_SEAMLESS_CONFORMANCE_PRESET` | Key within `presets.yaml` to load a conformance preset. | `strict-blocking` |
| `SEAMLESS_COORDINATOR_ID` | Human-readable identifier for the coordinator instance. | `local-dev` |
| `SEAMLESS_COORDINATOR_BIND` | Address and port that the coordinator binds to. | `0.0.0.0:8080` |
| `SEAMLESS_COORDINATOR_PROMETHEUS_PORT` | Port that exposes coordinator metrics. | `9102` |
| `SEAMLESS_COORDINATOR_REDIS_DSN` | Redis DSN used for distributed leases. | `redis://redis:6379/3` |
| `SEAMLESS_COORDINATOR_QUESTDB_DSN` | QuestDB DSN used for coverage queries. | `postgresql://qmtl:qmtl@questdb:8812/qdb` |
| `QUESTDB_POSTGRES_USER` | QuestDB PostgreSQL user. | `qmtl` |
| `QUESTDB_POSTGRES_PASSWORD` | QuestDB PostgreSQL password. | `qmtl` |
| `QUESTDB_POSTGRES_DB` | QuestDB database name. | `qdb` |
| `MINIO_ROOT_USER` | MinIO access key. | `seamless` |
| `MINIO_ROOT_PASSWORD` | MinIO secret key. | `seamless123` |
| `MINIO_BUCKET` | Bucket where artifacts will be written. | `seamless-artifacts` |
| `MINIO_CONSOLE_PORT` | Port for the MinIO console UI. | `9001` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | Optional OpenTelemetry collector endpoint. | _(empty)_ |

## SLA and Conformance Presets

The `presets.yaml` file defines reusable targets for
`qmtl.runtime.sdk.sla.SLAPolicy` and conformance enforcement. A typical loader
looks like this:

```python
import yaml
from qmtl.runtime.sdk.sla import SLAPolicy
from qmtl.runtime.sdk.seamless_data_provider import SeamlessDataProvider
from qmtl.runtime.sdk.conformance import ConformancePipeline

from qmtl.examples.seamless import open_presets

with open_presets() as handle:
    presets = yaml.safe_load(handle)

sla_config = presets["sla_presets"]["baseline"]["policy"]
conformance_config = presets["conformance_presets"]["strict-blocking"]

provider = SeamlessDataProvider(
    sla=SLAPolicy(**sla_config),
    partial_ok=conformance_config.get("partial_ok", False),
    conformance=ConformancePipeline(),
)
```

Adjust the preset key via the `QMTL_SEAMLESS_SLA_PRESET` and
`QMTL_SEAMLESS_CONFORMANCE_PRESET` variables so that runtime services can select
an appropriate policy without editing code.

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

4. Configure your QMTL runtime with the matching `QMTL_SEAMLESS_*` variables and
   point the SDK to the coordinator URL.
