from __future__ import annotations

"""
Lightweight DAG schema validator with version tagging.

Goals:
- Require an explicit schema version and ensure it is supported.
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
    - Version tag is required. Accept it at the DAG root as "schema_version" or
      at nodes as "schema_version".
    - Provided version must be one of SUPPORTED_VERSIONS.

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

    explicit = isinstance(version, str) and bool(version)
    if not explicit:
        errors.append(
            {
                "path": ["schema_version"],
                "message": "schema_version is required",
                "supported": sorted(SUPPORTED_VERSIONS),
            }
        )
        version = ""
    elif version not in SUPPORTED_VERSIONS:
        errors.append(
            {
                "path": ["schema_version"],
                "message": f"unsupported schema version: {version}",
                "supported": sorted(SUPPORTED_VERSIONS),
            }
        )

    return (len(errors) == 0), version, errors


__all__ = ["validate_dag", "SUPPORTED_VERSIONS"]
