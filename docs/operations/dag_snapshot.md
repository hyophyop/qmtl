# DAG Snapshot and Freeze

Use the `snapshot` subcommand to capture or verify a DAG definition.

```bash
qmtl service dagmanager snapshot --file dag.json --freeze
qmtl service dagmanager snapshot --file dag.json --verify
```

- `--freeze` writes a snapshot containing a SHA-256 hash and the DAG payload
  (default path: `dag.snapshot.json`).
- `--verify` checks that the current DAG matches a previously frozen snapshot
  and exits with a non-zero status on mismatch.

This workflow helps lock strategy or node versions by ensuring the DAG's
`code_hash` and `schema_hash` remain unchanged between runs.
