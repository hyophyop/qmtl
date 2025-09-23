"""Shared helpers for validating canonical node identities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from .crc import crc32_of_list
from .nodeid import compute_node_id

# Required node attributes that must be present for ``compute_node_id`` to be
# deterministic. The order here mirrors the legacy validator implementations to
# preserve error payload compatibility for downstream clients.
REQUIRED_NODE_FIELDS: tuple[str, ...] = (
    "node_type",
    "code_hash",
    "config_hash",
    "schema_hash",
    "schema_compat_id",
)


@dataclass(frozen=True, slots=True)
class MissingNodeField:
    """Record missing attributes for a node encountered during validation."""

    index: int
    missing: tuple[str, ...]
    node_id: str | None = None

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"index": self.index, "missing": list(self.missing)}
        if self.node_id:
            payload["node_id"] = self.node_id
        return payload


@dataclass(frozen=True, slots=True)
class NodeIdentityMismatch:
    """Report nodes whose supplied ``node_id`` does not match expectations."""

    index: int
    node_id: str
    expected: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "node_id": self.node_id,
            "expected": self.expected,
        }


class NodeValidationError(Exception):
    """Exception raised when canonical node validation fails."""

    def __init__(self, detail: dict[str, Any]) -> None:
        self.detail = detail
        message = detail.get("message") or detail.get("code") or "node validation error"
        super().__init__(message)

    @property
    def code(self) -> str:
        return str(self.detail.get("code", ""))

    @classmethod
    def missing_fields(cls, missing: Sequence[MissingNodeField]) -> "NodeValidationError":
        return cls(
            {
                "code": "E_NODE_ID_FIELDS",
                "message": "node_id validation requires node_type, code_hash, config_hash, schema_hash and schema_compat_id",
                "missing_fields": [item.to_payload() for item in missing],
                "hint": "Regenerate the DAG with an updated SDK so each node includes the hashes required by compute_node_id().",
            }
        )

    @classmethod
    def checksum_mismatch(
        cls, provided: int, computed: int
    ) -> "NodeValidationError":
        return cls({"code": "E_CHECKSUM_MISMATCH", "message": "node id checksum mismatch"})

    @classmethod
    def identity_mismatch(
        cls, mismatches: Sequence[NodeIdentityMismatch]
    ) -> "NodeValidationError":
        return cls(
            {
                "code": "E_NODE_ID_MISMATCH",
                "message": "node_id does not match canonical compute_node_id output",
                "node_id_mismatch": [item.to_payload() for item in mismatches],
                "hint": "Ensure legacy world-coupled or pre-BLAKE3 node_ids are regenerated using compute_node_id().",
            }
        )


@dataclass(frozen=True, slots=True)
class NodeValidationReport:
    """Structured result describing node identity validation findings."""

    provided_checksum: int
    computed_checksum: int
    node_ids: tuple[str, ...]
    missing_fields: tuple[MissingNodeField, ...]
    mismatches: tuple[NodeIdentityMismatch, ...]

    @property
    def checksum_valid(self) -> bool:
        return self.provided_checksum == self.computed_checksum

    @property
    def is_valid(self) -> bool:
        return not self.missing_fields and self.checksum_valid and not self.mismatches

    def raise_for_issues(self) -> None:
        if self.missing_fields:
            raise NodeValidationError.missing_fields(self.missing_fields)
        if not self.checksum_valid:
            raise NodeValidationError.checksum_mismatch(
                self.provided_checksum, self.computed_checksum
            )
        if self.mismatches:
            raise NodeValidationError.identity_mismatch(self.mismatches)


def validate_node_identity(
    nodes: Iterable[Any],
    provided_checksum: int,
    *,
    required_fields: Sequence[str] = REQUIRED_NODE_FIELDS,
) -> NodeValidationReport:
    """Validate nodes using canonical hashing rules.

    Parameters
    ----------
    nodes:
        Iterable of node mappings extracted from a DAG payload.
    provided_checksum:
        CRC32 supplied by the client covering node identifiers.
    required_fields:
        Node attributes that must be non-empty for ``compute_node_id`` to be
        deterministic.

    Returns
    -------
    NodeValidationReport
        Structured outcome describing checksum and mismatch findings. Call
        :meth:`NodeValidationReport.raise_for_issues` to raise a
        :class:`NodeValidationError` when validation fails.
    """

    node_ids_for_crc: list[str] = []
    missing_fields: list[MissingNodeField] = []
    mismatches: list[NodeIdentityMismatch] = []

    for index, node in enumerate(nodes):
        if not isinstance(node, Mapping):
            continue

        node_id = node.get("node_id")
        if not isinstance(node_id, str) or not node_id:
            node_ids_for_crc.append(str(node_id or ""))
            missing_fields.append(MissingNodeField(index=index, missing=("node_id",)))
            continue

        node_ids_for_crc.append(node_id)

        missing = tuple(field for field in required_fields if not node.get(field))
        if missing:
            missing_fields.append(
                MissingNodeField(index=index, node_id=node_id, missing=missing)
            )
            continue

        expected = compute_node_id(node)
        if node_id != expected:
            mismatches.append(
                NodeIdentityMismatch(index=index, node_id=node_id, expected=expected)
            )

    computed_checksum = crc32_of_list(node_ids_for_crc)
    return NodeValidationReport(
        provided_checksum=provided_checksum,
        computed_checksum=computed_checksum,
        node_ids=tuple(node_ids_for_crc),
        missing_fields=tuple(missing_fields),
        mismatches=tuple(mismatches),
    )


def enforce_node_identity(
    nodes: Iterable[Any], provided_checksum: int, *, required_fields: Sequence[str] = REQUIRED_NODE_FIELDS
) -> NodeValidationReport:
    """Validate nodes and raise :class:`NodeValidationError` on failure."""

    report = validate_node_identity(
        nodes, provided_checksum, required_fields=required_fields
    )
    report.raise_for_issues()
    return report


__all__ = [
    "MissingNodeField",
    "NodeIdentityMismatch",
    "NodeValidationError",
    "NodeValidationReport",
    "REQUIRED_NODE_FIELDS",
    "enforce_node_identity",
    "validate_node_identity",
]
