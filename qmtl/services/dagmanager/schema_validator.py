from __future__ import annotations

"""
Lightweight DAG schema validator with version tagging.

Goals:
- Accept legacy DAGs that omit a version tag to avoid breaking changes.
- If a version tag is present, ensure it is supported.
- Provide a structured error payload that callers can surface with a
  standardized error code (E_SCHEMA_INVALID).

This module intentionally keeps validation minimal and non‑disruptive.
It can be extended to perform stricter checks over time.
"""

from typing import Any, Iterable


SUPPORTED_VERSIONS: set[str] = {"v1", "1", "1.0"}


def _iter_nodes(dag: dict) -> Iterable[dict]:
    nodes = dag.get("nodes", [])
    if isinstance(nodes, list):
        for n in nodes:
            if isinstance(n, dict):
                yield n


def validate_dag(dag: dict) -> tuple[bool, str, list[dict[str, Any]]]:
    """Validate a DAG document and return (ok, version, errors).

    Rules (initial version):
    - Version tag is optional. If present at the DAG root as "schema_version"
      or at nodes as "schema_version", it must be one of SUPPORTED_VERSIONS.
    - If missing everywhere, default to "v1" and do not error.

    The returned errors are structured dictionaries suitable for HTTP error
    responses. Callers should raise a 400 with code "E_SCHEMA_INVALID" when
    ok is False.
    """
    errors: list[dict[str, Any]] = []

    # Prefer root‑level version if present; otherwise try the first node.
    version = dag.get("schema_version")
    if not isinstance(version, str) or not version:
        for node in _iter_nodes(dag):
            v = node.get("schema_version")
            if isinstance(v, str) and v:
                version = v
                break

    # Default to v1 to preserve backward compatibility
    if not isinstance(version, str) or not version:
        version = "v1"

    # If explicitly provided and unsupported, flag an error
    explicit = dag.get("schema_version") is not None or any(
        isinstance(n.get("schema_version"), str) and n.get("schema_version")
        for n in _iter_nodes(dag)
    )
    if explicit and (version not in SUPPORTED_VERSIONS):
        errors.append(
            {
                "path": ["schema_version"],
                "message": f"unsupported schema version: {version}",
                "supported": sorted(SUPPORTED_VERSIONS),
            }
        )

    return (len(errors) == 0), version, errors


__all__ = ["validate_dag", "SUPPORTED_VERSIONS"]

