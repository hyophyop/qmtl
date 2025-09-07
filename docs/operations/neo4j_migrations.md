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

