---
title: "World Registry"
tags: [world, registry]
author: "QMTL Team"
last_modified: 2026-04-03
---

{{ nav_links() }}

# World Registry

This page defines the CRUD and global-access contract for worlds as first-class objects independent of strategy submission. Normative envelopes remain in [World API Reference](../reference/api_world.md), while policy/activation/decision SSOT remains with [WorldService](../architecture/worldservice.md).

## 1. Design rules

- World IDs should be stable global slugs.
- WorldService owns the registry SSOT; Gateway only proxies and caches.
- Deletion is soft by default and should fail when active strategy sets still exist.

## 2. Data model

- `worlds`
  - `world_id`, `name`, `description`, `owner`, `labels[]`
  - `created_at`, `updated_at`
  - `default_policy_version`, `state`
  - `allow_live`, `circuit_breaker`
- `world_policies`
  - `(world_id, version)`
  - `yaml`, `checksum`, `status`, `created_by`, `created_at`
- `world_activation`
  - Redis key `world:<id>:active`
- `world_audit_log`
  - `event`, `actor`, `request`, `result`, `created_at`

## 3. API surface

- CRUD
  - `POST /worlds`
  - `GET /worlds`
  - `GET /worlds/{id}`
  - `PUT /worlds/{id}`
  - `DELETE /worlds/{id}`
- Policy versions
  - `POST /worlds/{id}/policies`
  - `GET /worlds/{id}/policies`
  - `GET /worlds/{id}/policies/{v}`
  - `POST /worlds/{id}/set-default?v=V`
- Runtime path
  - `GET /worlds/{id}/decide`
  - `GET /worlds/{id}/activation`
  - `POST /worlds/{id}/evaluate`
  - `POST /worlds/{id}/apply`
  - `GET /worlds/{id}/audit`

Sensitive endpoints (`apply`, activation override) require world-scoped RBAC.

## 4. CLI surface

```bash
qmtl world create --id crypto_mom_1h --file config/worlds/crypto_mom_1h.yml --set-default
qmtl world show crypto_mom_1h
qmtl world list --owner alice --state ACTIVE
qmtl world policy add crypto_mom_1h --file policy_v2.yml --version 2 --activate
qmtl world policy set-default crypto_mom_1h 2
qmtl world decide crypto_mom_1h --as-of 2025-08-28T09:00:00Z
qmtl world eval crypto_mom_1h
qmtl world apply crypto_mom_1h --plan plan.json --run-id $(uuidgen)
qmtl world delete crypto_mom_1h --force
```

## 5. Global access and consistency

- Services and runners read the world registry via REST/WS.
- Mutations should require etag/resource_version for optimistic locking.
- Cache refreshes fan out via `world.updated`-style events.

## 6. Operational notes

- Deletion should fail by default if active strategies still exist.
- Roll policy versions back via `set-default`; restore prior activation snapshots on apply failure.
- World dashboards should expose policy version, activation set, circuit state, and recent alerts.

{{ nav_links() }}
