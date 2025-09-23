from __future__ import annotations

"""Validation for node identifiers in submitted DAGs."""

from typing import Any, Iterable

from fastapi import HTTPException

from qmtl.foundation.common.node_validation import NodeValidationError, enforce_node_identity


class NodeIdentityValidator:
    """Ensure submitted node identities match canonical hashing rules."""

    def validate(self, dag: dict[str, Any], node_ids_crc32: int) -> None:
        nodes: Iterable[Any] = dag.get("nodes", [])
        try:
            enforce_node_identity(nodes, node_ids_crc32)
        except NodeValidationError as exc:  # pragma: no cover - exercised via tests
            raise HTTPException(status_code=400, detail=exc.detail) from exc
