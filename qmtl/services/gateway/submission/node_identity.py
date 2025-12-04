from __future__ import annotations

"""Validation for node identifiers in submitted DAGs."""

from typing import Any, Iterable

from fastapi import HTTPException

from qmtl.foundation.common import (
    NodeValidationError,
    NodeValidationReport,
    validate_node_identity,
)
from qmtl.services.gateway import metrics as gw_metrics


class NodeIdentityValidator:
    """Ensure submitted node identities match canonical hashing rules."""

    def validate(
        self, dag: dict[str, Any], node_ids_crc32: int
    ) -> NodeValidationReport:
        nodes_iter: Iterable[Any] = dag.get("nodes", [])
        nodes = list(nodes_iter)
        report = validate_node_identity(nodes, node_ids_crc32)
        gw_metrics.record_node_identity_report(report, nodes)
        try:
            report.raise_for_issues()
            return report
        except NodeValidationError as exc:  # pragma: no cover - exercised via tests
            raise HTTPException(status_code=400, detail=exc.detail) from exc
