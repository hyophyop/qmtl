# Seamless Full-Stack Bundle (Distributed Backfill as a First-Class Service)

## Background & Goals
- Today the distributed backfill coordinator lives in its own Compose bundle; when `coordinator_url` is empty the SDK silently falls back to an in-memory stub. Gateway/DAG Manager/WorldService already follow a dev→in-memory, prod→external-required rule.
- Goal: promote the distributed backfill coordinator to the same first-class tier as Gateway/DAG Manager/WorldService and ship a prod full-stack bundle (Compose/Helm) that includes it. Keep dev safe with stubs/local bundles, but prevent prod from silently downgrading.

## Scope
- Service posture: treat the coordinator as core; decide whether ControlBus should be exposed as a first-class service.
- Env behaviour: define dev/prod defaults, validation, and fallback rules.
- Deployment assets: prod all-in Compose/Helm (Gateway, DAG Manager, WorldService, Coordinator, ControlBus, Redis/QuestDB/Neo4j/Kafka/Postgres/MinIO). Keep `operations/seamless/docker-compose.seamless.yml` for dev/partial stacks; the supporting doc is [Seamless Stack Templates](../operations/seamless_stack.md).
- Out of scope: coordinator protocol changes, SLA/conformance schema changes.

## Design

### 1) Service posture & ControlBus
- Distributed backfill coordinator: treated as a core “data/submit path” service alongside Gateway/DAG Manager/WorldService.
- ControlBus: default to Redpanda (single-node for dev, 3-node overlay for prod). Include it in the full-stack bundle; dev may still use in-memory/local Redis-only mode when ControlBus is not required.
- Dependencies: coordinator requires Redis (locks/rate-limit), QuestDB (coverage/backfill meta), MinIO/S3 (artifacts), and an HTTP port; the full bundle supplies these by default.

### 2) Environment rules
- Dev profile:
  - Default: when `coordinator_url` is absent, keep the in-memory stub; log a warning that prod requires a URL.
  - Option: provide a light `docker-compose.dev.override.yml` to spin up only the coordinator + minimal deps.
- Prod profile:
  - Missing `seamless.coordinator_url` → `qmtl config validate --target all` error (no fallback).
  - Runtime init: coordinator health check uses bounded retries (e.g., 3 attempts over ~30s) then fails startup; no stub fallback.
  - Ship `operations/config/prod.full.yml` with coordinator/QuestDB/Redis/MinIO/ControlBus/Kafka/Neo4j/Postgres DSNs populated.

### 3) Deployment bundle (prod default)
- Single Compose/Helm bundle includes:
  - `gateway`, `dagmanager`, `worldservice`
  - `seamless-coordinator` (HTTP 8080/metrics, depends on Redis/QuestDB/MinIO)
  - `controlbus` (Kafka/Redpanda + Zookeeper or single Redpanda) — shared by gw/dagmanager/ws
  - `redis`, `postgres` (gateway DB), `neo4j` (dagmanager), `questdb` (data), `minio` (artifacts)
- Dev override: keep gw/dagmanager/ws in in-memory/local mode, allow running without a coordinator via `-f docker-compose.full.yml -f docker-compose.dev.override.yml`.
- Preserve the existing `operations/seamless/docker-compose.seamless.yml` as a sample/partial stack; prod defaults point to the full bundle.

### 4) Config & validation
- Add Seamless checks to `config validate`:
  - Prod: missing `coordinator_url`, missing Redis/QuestDB/MinIO DSNs, or failed coordinator health → error.
  - Dev: missing `coordinator_url` → warning.
- Runtime init: coordinator creation failure in prod → forbid stub fallback; raise and exit.
- Sample configs: add `operations/config/prod.full.yml` and `operations/config/dev.full.yml`; docs show `--config` usage.

### 5) Migration steps
1) Docs: update Seamless/Operations guides to make the full-stack bundle the prod default.  
2) Config templates: add dev/prod full templates in `operations/config`, with coordinator URL/DSNs prefilled.  
3) Validation hook: extend `config validate` with Seamless checks; forbid prod fallback.  
4) Compose/Helm: add `operations/docker-compose.full.yml` (or a Helm chart); keep the existing single-purpose bundle as a sample.  
5) Runtime guard: introduce profile-aware stub blocking in `_create_default_coordinator` for prod.  
6) Rollout: verify in staging with the full bundle, then roll out to prod; publish a short upgrade guide for users of the standalone coordinator bundle.

### 6) Implementation checklist (concrete TODOs)
- Config templates: create `operations/config/dev.full.yml` (coordinator optional, local defaults) and `operations/config/prod.full.yml` (all DSNs populated, coordinator required).
- Validation: extend `qmtl config validate --target all` to enforce `seamless.coordinator_url` + Redis/QuestDB/MinIO availability in prod; warn only in dev.
- Runtime guardrails: add profile-aware stub blocking + bounded health retries to `_create_default_coordinator`.
- Bundles: add `operations/docker-compose.full.yml` plus `docker-compose.dev.override.yml`; mirror the same structure in a Helm chart.
- Docs: update `operations/seamless_stack.md`, `operations/docker.md`, and Seamless guides to point prod to the full bundle; include upgrade notes for legacy standalone coordinator users.

### 7) Reference values & health checks
- Coordinator: `http://seamless-coordinator:8080`, health endpoint `/healthz`, retries 3x with ~10s backoff (total ~30s) before failing startup.
- Redis (locks/ratelimit): `redis://redis:6379/3`, keys prefixed `seamless:*`.
- QuestDB: `postgresql://questdb:8812/qmtl`, tables prefixed `seamless_*`.
- MinIO: `http://minio:9000`, bucket `qmtl-seamless`, prefix `artifacts/`.
- ControlBus (Redpanda): broker `redpanda:9092`, topic prefix `qmtl.controlbus.*`.

### 6) Shared dependency isolation
- Redis: assign per-service DB indexes or prefixes (`seamless:*`, `gateway:*`, `dagmanager:*`), and keep coordinator lock/rate-limit keys separate from other caches. For prod, prefer a dedicated Redis cluster or logical DB for coordinator if noisy neighbours are expected.
- Kafka/ControlBus: enforce topic prefixes (e.g., `qmtl.controlbus.*`) and ACLs; avoid reusing a shared ops bus without topic isolation.
- MinIO/S3: separate buckets or prefixes for Seamless artifacts vs other workloads; enforce IAM policies so coordinator writes are scoped.
- QuestDB: isolate tables used by the coordinator (coverage/meta) with a fixed prefix or dedicated database to avoid collisions with strategy data.
- Network/resource isolation: in prod, place coordinator and its dependencies on an internal network segment; set per-service quotas/limits in Compose/Helm to avoid starvation from other modules.

### 8) Managed dependencies
- If QuestDB/MinIO are managed services, document override snippets (URLs/creds) and strip them from the bundle via overrides.
- Keep ControlBus (Redpanda) defaulted in-bundle; if using an external Kafka, supply topic prefix/ACL guidance and health probes.
- Ensure IAM separation for buckets/prefixes and DB users when reusing shared infra.

### 9) Open points
- Externalizing QuestDB/MinIO: decide whether the full bundle should omit them when managed services exist; default to “included”, with overrides documented.
