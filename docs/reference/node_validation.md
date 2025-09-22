# Node Identity Validation

`qmtl.common.node_validation` centralizes the checksum and field checks that
back Gateway ingestion, CLI tooling, and SDK dry-run paths. The helpers wrap the
canonical [`compute_node_id`](../architecture/gateway.md) routine so every entry
point enforces identical contracts.

## API Summary

- `validate_node_identity(nodes, provided_checksum)` returns a
  `NodeValidationReport` describing the computed CRC32 checksum, any missing
  fields, and mismatched identifiers.
- `enforce_node_identity(nodes, provided_checksum)` performs the same
  validation but raises a `NodeValidationError` when the payload is invalid.
- `NodeValidationReport.raise_for_issues()` promotes report findings to a
  `NodeValidationError`, allowing callers to defer the exception until after
  collecting diagnostics.
- `REQUIRED_NODE_FIELDS` exposes the tuple of attributes (`node_type`,
  `code_hash`, `config_hash`, `schema_hash`, `schema_compat_id`) that must be
  non-empty for deterministic hashing.

The `NodeValidationError.detail` payload mirrors FastAPI responses emitted by
`NodeIdentityValidator` to preserve backwards compatibility for REST clients.

## Error Codes

| Code | Description |
| ---- | ----------- |
| `E_NODE_ID_FIELDS` | One or more required attributes are missing. The error payload contains a `missing_fields` list plus a remediation hint. |
| `E_CHECKSUM_MISMATCH` | The provided CRC32 checksum does not match the computed value derived from the submitted node identifiers. |
| `E_NODE_ID_MISMATCH` | At least one node's `node_id` differs from the canonical `compute_node_id` output. The error payload enumerates the mismatched nodes. |

## Usage Example

```python
from qmtl.common import crc32_of_list, enforce_node_identity

def validate_payload(dag: dict[str, object], checksum: int) -> None:
    nodes = dag.get("nodes", [])
    enforce_node_identity(nodes, checksum)

dag = {"nodes": [some_node]}
checksum = crc32_of_list([node["node_id"] for node in dag["nodes"]])
validate_payload(dag, checksum)
```

The Gateway submission pipeline and CLI now share this module, ensuring every
consumer receives consistent diagnostics and hint text.
