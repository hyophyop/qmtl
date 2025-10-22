# Neo4j Schema Initialization

This guide covers initializing and re-running the DAG Manager’s Neo4j schema setup.

- Command: `qmtl service dagmanager neo4j-init`
- Behavior: idempotent — safe to re-run at any time
- Scope: creates constraints and indexes used by high-traffic queries

## What It Creates

The initializer applies the following operations if they do not already exist:

- Compute node primary key: unique constraint on `(:ComputeNode {node_id})`
- Queue topic index: index on `(:Queue {topic})`
- Queue interval index: index on `(:Queue {interval})`
- Compute tags index: index on `(:ComputeNode {tags})`
- Buffering sweep index: index on `(:ComputeNode {buffering_since})`

These support fast paths for:

- Node lookups by `node_id` and topic-bound routing
- Tag→queue resolution with interval filters
- Periodic sweeps of buffering nodes

## Usage

```bash
qmtl service dagmanager neo4j-init \
  --uri bolt://localhost:7687 \
  --user neo4j \
  --password neo4j
```

- Uses `CREATE … IF NOT EXISTS` to ensure idempotency.
- No data is modified beyond schema metadata.

## Performance Note

The added indexes are selected for the DAG Manager’s representative queries. On
medium-sized graphs, these keep p95 query latencies within the target envelope.
If your workload deviates significantly (e.g., additional label/property filters),
consider adding specific indexes following the same pattern.
