# Neo4j Migrations & Rollback

This page describes how to initialize, inspect, and roll back the DAG Manager’s Neo4j schema.

## Initialize (idempotent)

All DDL uses `IF NOT EXISTS`, so re-running is safe:

```
qmtl dagmanager neo4j-init \
  --uri bolt://localhost:7687 --user neo4j --password neo4j
```

## Export current schema

```
qmtl dagmanager export-schema \
  --uri bolt://localhost:7687 --user neo4j --password neo4j --out schema.cypher
```

## Rollback (drop created objects)

Drops the constraints and indexes created by `neo4j-init` using `DROP ... IF EXISTS`:

```
qmtl dagmanager neo4j-rollback \
  --uri bolt://localhost:7687 --user neo4j --password neo4j
```

Use with caution in lower environments; production rollback should follow a controlled migration plan.

## WorldNodeRef Domain Expansion (Backtest/Dryrun/Live Isolation)

### Objective

- Promote `execution_domain` to a first-class component of the `WorldNodeRef` composite key.
- Allow multiple domain-scoped records per `(world_id, node_id)` without disrupting existing readers.

### Zero-Downtime Approach

1. **Deploy Read/Write Compatible Code**
   - Ensure Gateway and WorldService nodes are running the release that understands multi-domain buckets. The in-memory `Storage` layer auto-normalises legacy payloads and defaults unknown domains to `live`.
2. **Add/Update Neo4j Constraints**
   - `CREATE CONSTRAINT world_node_ref_key IF NOT EXISTS
     FOR (w:WorldNodeRef)
     REQUIRE (w.world_id, w.node_id, w.execution_domain) IS UNIQUE;`
   - Existing single-domain uniques (if any) can remain during the rollout; drop them only after backfill.
3. **Backfill / Lazy Migration**
   - _Lazy path_: allow traffic to touch existing nodes. The service converts legacy records (`execution_domain` missing) to the default `live` domain on read.
   - _Backfill path_: run a Cypher job to clone each `WorldNodeRef` into explicit domain buckets:
     ```cypher
     MATCH (n:WorldNodeRef)
     WHERE n.execution_domain IS NULL OR n.execution_domain = ""
     SET n.execution_domain = "live";
     ```
   - For worlds that require pre-populated `backtest`/`dryrun` buckets, replay the Gateway "world node upsert" task per domain.
4. **Validation**
   - Sample `MATCH (n:WorldNodeRef) RETURN n.execution_domain, count(*) ORDER BY n.execution_domain;` to ensure the histogram aligns with expectations.
   - Automated coverage: `tests/worldservice/test_worldservice_api.py::test_world_nodes_execution_domains_and_legacy_migration` exercises the lazy conversion path via the public API.
   - WorldService appends `world_node_bucket_normalized` audit events when legacy payloads are promoted on-demand. Monitor `GET /worlds/{id}/audit` to confirm conversions complete without manual intervention.

### Rollback

- Neo4j rollback remains `DROP CONSTRAINT world_node_ref_key IF EXISTS;` followed by restoring the prior snapshot.
- Because the application tolerates missing `execution_domain`, the rollback is a metadata change; data remains valid.

## EvalKey Recalculation Plan

### Objective

- Extend the validation cache key to include `execution_domain` for strict isolation.
- Expire legacy entries hashed without the domain component.

### Strategy

1. **Deploy compatible services** that recompute EvalKeys using the new tuple `(node_id, world_id, execution_domain, contract_id, dataset_fingerprint, code_version, resource_policy)`.
2. **Lazy invalidation**
   - During lookup the service rehashes the context; mismatched keys are dropped and the caller re-runs validation.
   - Tests cover this path via `tests/worldservice/test_validation_cache.py::test_validation_cache_legacy_payloads_are_normalised_and_invalidated`.
   - Canonical execution domain coercion is verified by `tests/worldservice/test_validation_cache.py::test_validation_cache_normalises_execution_domain_on_set` to prevent divergent cache buckets during the rollout.
   - The audit log records `validation_cache_bucket_normalized` when payloads are rewritten and `validation_cache_invalidated` once stale EvalKeys are purged, providing an operational breadcrumb during rollout.
3. **Optional proactive purge**
   - `MATCH (v:Validation) REMOVE v.eval_key_without_domain;` if a transitional property exists.
   - To force re-validation immediately, delete the `Validation` nodes: `MATCH (v:Validation) WHERE v.version < $cutover REMOVE v` (adjust predicate to local schema).

### Verification

- Monitor the validation cache miss metrics; a spike is expected during rollout and should converge as caches repopulate.
- Confirm new entries have the `execution_domain` field present in Neo4j snapshots.
