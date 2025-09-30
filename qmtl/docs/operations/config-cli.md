---
title: "Config CLI"
tags: [cli, config, operations]
author: "QMTL Team"
last_modified: 2025-09-24
---

{{ nav_links() }}

# Config CLI (Validate, Export, Launch)

Use `qmtl config` to verify service configuration files and generate
environment assignments for Gateway and DAG Manager. The workflow pairs with
the backend quickstart so operators can lint YAML before starting services.

## Validate configuration files

Run validation against a configuration file. The `--offline` flag skips
connectivity checks and reports which external services are disabled:

```bash
uv run qmtl config validate --config qmtl/examples/qmtl.yml --offline
```

Sample output:

```
gateway:
  redis         WARN   Offline mode: skipped Redis ping for redis://localhost:6379
  database      OK     SQLite ready at ./qmtl.db
  controlbus    OK     ControlBus disabled; no brokers/topics configured
  worldservice  OK     WorldService proxy disabled

dagmanager:
  neo4j       OK     Neo4j disabled; using memory repository
  kafka       OK     Kafka DSN not configured; using in-memory queue manager
  controlbus  OK     ControlBus disabled; no brokers/topics configured
```

Warnings denote skipped checks or fallbacks. Any `ERROR` line exits with a
non-zero status so CI/CD jobs can fail fast.

## Export environment assignments

Generate a shell script that exports configuration as environment variables
(which services read before applying defaults):

```bash
uv run qmtl config env export --config qmtl/examples/qmtl.yml > .env.qmtl
```

The first lines show metadata and the managed variables. Secrets are omitted by
default—re-run with `--include-secret` to inline them:

```
export QMTL_CONFIG_SOURCE=/workspace/qmtl/qmtl/examples/qmtl.yml
export QMTL_CONFIG_EXPORT='{"generated_at": "2025-09-24T05:42:58Z", "include_secret": false, "secrets_omitted": true, "shell": "posix", "variables": 19}'
# Secrets omitted (QMTL__GATEWAY__DATABASE_DSN, QMTL__GATEWAY__REDIS_DSN, QMTL__DAGMANAGER__NEO4J_PASSWORD). Re-run with --include-secret to include them.
export QMTL__GATEWAY__COMMITLOG_GROUP=gateway-commit
export QMTL__GATEWAY__COMMITLOG_TOPIC=gateway.ingest
... (truncated)
```

Use `source .env.qmtl` (POSIX) or `.\. .env.qmtl` (PowerShell) to load the
environment before launching services. For auditing, `qmtl config env show`
prints the active variables (masking secrets) and `qmtl config env clear`
produces commands to unset them.

## Environment variable fallback

Gateway and DAG Manager resolve configuration in this order:

1. `--config /path/to/qmtl.yml` passed on the command line.
2. `QMTL_CONFIG_FILE=/path/to/qmtl.yml` in the process environment.
3. `qmtl.yml` or `qmtl.yaml` in the current working directory.
4. Built-in defaults baked into the service configuration classes.

`qmtl config env export` writes two helper variables:

- `QMTL_CONFIG_SOURCE` – absolute path of the exported YAML for logging.
- `QMTL_CONFIG_EXPORT` – JSON metadata (timestamp, variable count, whether
  secrets were omitted). Services include this in warnings when sections are
  missing so operators know the environment was generated from an older export.

Combine them with `QMTL_CONFIG_FILE` to let daemons pick the YAML without
repeating `--config`:

```bash
source .env.qmtl
export QMTL_CONFIG_FILE=$PWD/qmtl/examples/qmtl.yml
```

If `QMTL_CONFIG_FILE` points to a missing file, the services log a warning and
fall back to the next rule. This prevents deployments from silently using stale
paths.

## End-to-end launch sequence

Putting it together:

```bash
# 1. Validate the configuration (fails on hard errors).
uv run qmtl config validate --config qmtl/examples/qmtl.yml --offline

# 2. Export and source environment overrides.
uv run qmtl config env export --config qmtl/examples/qmtl.yml > .env.qmtl
source .env.qmtl
export QMTL_CONFIG_FILE=$PWD/qmtl/examples/qmtl.yml

# 3. Launch services (env fallback picks up the same config file).
qmtl service gateway
qmtl service dagmanager server
```

WorldService continues to rely on `QMTL_WORLDSERVICE_*` variables. The config
CLI focuses on Gateway and DAG Manager overrides so the entire stack can start
with consistent settings.

{{ nav_links() }}
