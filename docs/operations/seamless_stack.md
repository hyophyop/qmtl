# Seamless Stack Templates

This runbook describes how to bootstrap a Seamless deployment using the
templates under `operations/seamless/`.

## Directory Overview

The repository ships the following artifacts:

- `operations/seamless/docker-compose.seamless.yml` – Compose bundle that starts
  the Seamless backfill coordinator, QuestDB, Redis, and MinIO.
- `operations/seamless/.env.example` – Baseline environment variables for the
  Compose stack and Seamless SDK.
- `qmtl/examples/seamless/presets.yaml` – SLA and conformance presets aligned
  with the QMTL SDK defaults. A convenience copy remains under
  `operations/seamless/presets.yaml` for operators working from the repository
  checkout.
- `operations/seamless/README.md` – Detailed documentation of services and
  configuration options.

Copy `.env.example` to `.env` and tune any secrets before launching the stack.

## Launching the Stack

Run the following commands from the repository root:

```bash
cp operations/seamless/.env.example operations/seamless/.env

docker compose -f operations/seamless/docker-compose.seamless.yml up -d
```

Verify the services:

- Coordinator health probe – `curl http://localhost:8080/healthz`
- QuestDB UI – `http://localhost:9000`
- MinIO console – `http://localhost:9001`

Adjust `operations/config/*.yml` to point at your coordinator, select the
desired SLA/conformance presets, and configure artifact capture. The
`seamless` section drives these runtime behaviours.

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
