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

## WorldNodeRef Execution Domain Expansion (online)

The World View Graph (WVG) now scopes `WorldNodeRef` records by
`execution_domain`. Existing deployments may still hold legacy rows that only
contain `(world_id, node_id)` and an obsolete `last_eval_key`. Perform the
following zero-downtime sequence:

1. **Schema** — add the new property and composite key. Example Cypher executed
   through the usual migration harness:

   ```cypher
   // allow mixed state while the backfill runs
   CREATE CONSTRAINT wvg_world_node_ref_domain IF NOT EXISTS
   FOR (n:WorldNodeRef)
   REQUIRE (n.world_id, n.node_id, n.execution_domain) IS UNIQUE;

   CALL apoc.util.validatePredicate(
     n.execution_domain IS NULL,
     'execution_domain must be populated during domain backfill',
     [n]
   )
   YIELD value
   RETURN value;
   ```

2. **Backfill** — stream the legacy rows, convert them to domain-aware
   dictionaries using `Storage.backfill_world_node_refs`, and write the results
   back with the preferred driver (Bolt/OGM). The helper performs the
   EvalKey recalculation to ensure cache isolation:

   ```python
   import asyncio

   from qmtl.worldservice.storage import Storage

   storage = Storage()
   storage_loop = asyncio.get_event_loop()

   legacy_rows = fetch_legacy_world_node_refs()  # yields dicts
   storage_loop.run_until_complete(
       storage.load_legacy_world_node_refs(legacy_rows, default_domain="live")
   )
   upgraded = storage_loop.run_until_complete(storage.backfill_world_node_refs())
   persist_world_node_refs(upgraded)
   ```

   The tests in `tests/worldservice/test_worldservice_migrations.py` exercise the
   conversion logic and EvalKey recomputation.

3. **Lazy guard** — the storage shim keeps a lazy-upgrade path via
   `Storage.get_world_node_ref` and `Storage.list_world_node_refs`. Any call that
   touches a legacy row upgrades it on-the-fly, recalculates the EvalKey using
   the formula `blake3(NodeID || WorldID || ExecutionDomain || ContractID ||
   DatasetFingerprint || CodeVersion || ResourcePolicy)`, and emits an audit
   event. This allows the service to stay online while the bulk backfill runs or
   if stragglers appear later.

4. **Cleanup** — once the migration finishes and monitoring confirms that no
   lazy upgrades are occurring, drop temporary guards (if any) and enforce the
   new constraint as mandatory in policy.

Because both the eager backfill and the lazy guard operate under live traffic,
no maintenance window is required. Monitor the audit log and the
`world_node_ref_migrated` events to track progress.

