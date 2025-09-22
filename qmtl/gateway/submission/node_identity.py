from __future__ import annotations

"""Validation for node identifiers in submitted DAGs."""

from typing import Any, Iterable

from fastapi import HTTPException

from qmtl.common import crc32_of_list, compute_node_id


class NodeIdentityValidator:
    """Ensure submitted node identities match canonical hashing rules."""

    def validate(self, dag: dict[str, Any], node_ids_crc32: int) -> None:
        nodes = dag.get("nodes", [])
        node_ids_for_crc: list[str] = []
        missing_fields: list[dict[str, Any]] = []
        mismatches: list[dict[str, str | int]] = []

        for idx, node in enumerate(nodes):
            if not isinstance(node, dict):
                continue
            nid = node.get("node_id")
            if not isinstance(nid, str) or not nid:
                node_ids_for_crc.append(str(nid or ""))
                missing_fields.append({"index": idx, "missing": ["node_id"]})
                continue

            node_ids_for_crc.append(nid)
            required = {
                "node_type": node.get("node_type"),
                "code_hash": node.get("code_hash"),
                "config_hash": node.get("config_hash"),
                "schema_hash": node.get("schema_hash"),
                "schema_compat_id": node.get("schema_compat_id"),
            }
            missing = [field for field, value in required.items() if not value]
            if missing:
                missing_fields.append(
                    {"index": idx, "node_id": nid, "missing": missing}
                )
                continue

            expected = compute_node_id(node)
            if nid != expected:
                mismatches.append({"index": idx, "node_id": nid, "expected": expected})

        crc = crc32_of_list(node_ids_for_crc)
        if missing_fields:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "E_NODE_ID_FIELDS",
                    "message": "node_id validation requires node_type, code_hash, config_hash, schema_hash and schema_compat_id",
                    "missing_fields": missing_fields,
                    "hint": "Regenerate the DAG with an updated SDK so each node includes the hashes required by compute_node_id().",
                },
            )

        if crc != node_ids_crc32:
            raise HTTPException(
                status_code=400,
                detail={"code": "E_CHECKSUM_MISMATCH", "message": "node id checksum mismatch"},
            )

        if mismatches:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "E_NODE_ID_MISMATCH",
                    "message": "node_id does not match canonical compute_node_id output",
                    "node_id_mismatch": mismatches,
                    "hint": "Ensure legacy world-coupled or pre-BLAKE3 node_ids are regenerated using compute_node_id().",
                },
            )
