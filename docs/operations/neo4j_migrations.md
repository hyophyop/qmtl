---
title: "Neo4j Schema Migrations"
tags: []
author: "QMTL Team"
last_modified: 2025-09-07
---

{{ nav_links() }}

# Neo4j Schema Migrations

This page documents how the DAG Manager initializes and maintains the Neo4j
graph schema in an idempotent, re‑runnable manner.

## Goals

- Idempotent CLI: `qmtl dagmanager neo4j-init` can be safely re‑run.
- Operational safety: constraints and indexes are created using
  `IF NOT EXISTS` guards to avoid errors when schema already exists.
- Minimal downtime: migrations only add constraints/indexes and do not drop
  existing ones.

## What the CLI does

The command connects to Neo4j and applies a small set of schema statements.
The current set is defined in code and validated by tests:

```cypher
CREATE CONSTRAINT compute_pk IF NOT EXISTS
ON (c:ComputeNode) ASSERT c.node_id IS UNIQUE;

CREATE INDEX kafka_topic IF NOT EXISTS FOR (q:Queue) ON (q.topic);
```

See Architecture → DAG Manager → “Indexes & Constraints” for background and
additional context.

## Usage

```bash
# default bolt endpoint, neo4j/neo4j
qmtl dagmanager neo4j-init

# custom connection parameters
qmtl dagmanager neo4j-init \
  --uri bolt://db.example:7687 \
  --user neo4j \
  --password 's3cret'
```

Re‑running the command is safe thanks to `IF NOT EXISTS` guards. To preview the
effective statements for audit purposes:

```bash
qmtl dagmanager export-schema --uri bolt://localhost:7687 --out schema.cql
```

## Performance note

Representative DAG lookups are expected to stay within p95 ≤ 50 ms on a
moderate dataset. If lookups exceed this budget, consider adding targeted
indexes based on your workload. Keep additions minimal and aligned with the
data model documented under Architecture.

{{ nav_links() }}

