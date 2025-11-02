---
title: "Config CLI"
tags: [cli, config, operations]
author: "QMTL Team"
last_modified: 2025-10-12
---

{{ nav_links() }}

# Config CLI (Validate & Launch)

Use `qmtl config validate` to verify Gateway and DAG Manager configuration
before starting services. The command reads a unified YAML file and fails fast
when required sections are missing or when a validation check reports an
`ERROR` severity.

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

Warnings denote skipped checks or fallbacks. Any `ERROR` line exits with status
code `1` so CI/CD jobs can fail fast. When a configuration omits a requested
section (for example the `dagmanager` block), the CLI prints a descriptive
message and exits with status code `2` before executing any validations.

## Launch sequence

Services consume the same YAML directly. Provide the path on the command line or
copy it to `qmtl.yml` so long-running daemons can discover it automatically:

```bash
# Validate first.
uv run qmtl config validate --config qmtl/examples/qmtl.yml --offline

# Launch services using the same YAML.
qmtl service gateway --config qmtl/examples/qmtl.yml
qmtl service dagmanager server --config qmtl/examples/qmtl.yml
```

When no configuration file is discovered the services log a warning and fall
back to built-in defaults, ensuring operators can spot stale paths during
startup.

{{ nav_links() }}
