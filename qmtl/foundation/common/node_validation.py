"""Shared helpers for validating canonical node identities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from .crc import crc32_of_list
from .nodeid import compute_node_id
from .nodespec import normalize_schema_compat_id
from .tagquery import canonical_tag_query_params_from_node

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


@dataclass(frozen=True, slots=True)
class SchemaCompatConflict:
    """Report nodes whose schema_compat_id conflicts with legacy schema_id."""

    index: int
    schema_compat_id: str
    schema_id: str
    node_id: str | None = None

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "index": self.index,
            "schema_compat_id": self.schema_compat_id,
            "schema_id": self.schema_id,
        }
        if self.node_id:
            payload["node_id"] = self.node_id
        return payload


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
                "hint": "Regenerate node_ids using compute_node_id() with all canonical fields populated.",
            }
        )

    @classmethod
    def schema_conflict(
        cls, conflicts: Sequence[SchemaCompatConflict]
    ) -> "NodeValidationError":
        return cls(
            {
                "code": "E_SCHEMA_COMPAT_MISMATCH",
                "message": "schema_compat_id and schema_id must match when both are provided",
                "schema_conflicts": [item.to_payload() for item in conflicts],
                "hint": "Send only schema_compat_id or ensure legacy schema_id matches it.",
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
    schema_conflicts: tuple[SchemaCompatConflict, ...]

    @property
    def checksum_valid(self) -> bool:
        return self.provided_checksum == self.computed_checksum

    @property
    def is_valid(self) -> bool:
        return (
            not self.missing_fields
            and not self.schema_conflicts
            and self.checksum_valid
            and not self.mismatches
        )

    def raise_for_issues(self) -> None:
        if self.missing_fields:
            raise NodeValidationError.missing_fields(self.missing_fields)
        if self.schema_conflicts:
            raise NodeValidationError.schema_conflict(self.schema_conflicts)
        if not self.checksum_valid:
            raise NodeValidationError.checksum_mismatch(
                self.provided_checksum, self.computed_checksum
            )
        if self.mismatches:
            raise NodeValidationError.identity_mismatch(self.mismatches)


def _missing_tagquery_requirements(node: Mapping[str, Any]) -> tuple[str, ...]:
    """Return TagQuery-specific required fields that are absent."""

    try:
        canonical_tag_query_params_from_node(
            node, require_tags=True, require_interval=True
        )
    except ValueError as exc:
        text = str(exc).lower()
        missing: list[str] = []
        if "tag" in text:
            missing.append("tags")
        if "interval" in text:
            missing.append("interval")
        return tuple(missing)
    return ()


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
    schema_conflicts: list[SchemaCompatConflict] = []

    for index, node in enumerate(nodes):
        if not isinstance(node, Mapping):
            continue

        node_id = node.get("node_id")
        node_type = str(node.get("node_type") or "")
        if not isinstance(node_id, str) or not node_id:
            node_ids_for_crc.append(str(node_id or ""))
            missing_fields.append(MissingNodeField(index=index, missing=("node_id",)))
            continue

        node_ids_for_crc.append(node_id)

        legacy_schema_id = (
            node.get("schema_id") if "schema_id" in node else None
        )
        try:
            normalized_schema_compat_id = normalize_schema_compat_id(
                node.get("schema_compat_id"), fallback=legacy_schema_id
            )
        except ValueError:
            schema_conflicts.append(
                SchemaCompatConflict(
                    index=index,
                    node_id=node_id,
                    schema_compat_id=str(node.get("schema_compat_id") or ""),
                    schema_id=str(legacy_schema_id or ""),
                )
            )
            continue

        missing_list = [field for field in required_fields if not node.get(field)]
        if "schema_compat_id" in missing_list and normalized_schema_compat_id:
            missing_list.remove("schema_compat_id")
        if node_type == "TagQueryNode":
            missing_list.extend(_missing_tagquery_requirements(node))

        if missing_list:
            missing = tuple(dict.fromkeys(missing_list))
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
        schema_conflicts=tuple(schema_conflicts),
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
    "SchemaCompatConflict",
    "REQUIRED_NODE_FIELDS",
    "enforce_node_identity",
    "validate_node_identity",
]
