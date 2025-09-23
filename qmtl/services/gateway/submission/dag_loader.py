from __future__ import annotations

"""Decode and validate strategy DAG payloads."""

import base64
import json
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException


@dataclass
class LoadedDag:
    """Container for decoded DAG structures."""

    dag: dict[str, Any]
    dag_json: str


class DagLoader:
    """Decode base64-encoded DAG submissions and validate schema."""

    def __init__(self) -> None:
        pass

    def decode(self, dag_payload: str) -> LoadedDag:
        """Return parsed DAG from ``dag_payload`` which may be base64 encoded."""

        try:
            dag_bytes = base64.b64decode(dag_payload)
            decoded = json.loads(dag_bytes.decode())
        except Exception:
            decoded = json.loads(dag_payload)
        return LoadedDag(dag=decoded, dag_json=dag_payload)

    def validate(self, dag: dict[str, Any]) -> None:
        from qmtl.services.dagmanager.schema_validator import validate_dag

        ok, _version, verrors = validate_dag(dag)
        if not ok:
            raise HTTPException(
                status_code=400,
                detail={"code": "E_SCHEMA_INVALID", "errors": verrors},
            )

    def load(self, dag_payload: str) -> LoadedDag:
        """Decode and validate ``dag_payload`` returning ``LoadedDag``."""

        loaded = self.decode(dag_payload)
        self.validate(loaded.dag)
        return loaded
