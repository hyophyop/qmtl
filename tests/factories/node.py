"""Factories for constructing canonical DAG nodes in tests."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Mapping

from qmtl.common import compute_node_id


def _default_node_template() -> dict[str, Any]:
    return {
        "node_type": "TagQueryNode",
        "code_hash": "blake3:code",
        "config_hash": "blake3:config",
        "schema_hash": "blake3:schema",
        "schema_compat_id": "schema:v1",
        "params": {"universe": "us_equities"},
        "inputs": [],
    }


@dataclass(slots=True)
class NodeFactory:
    """Build canonical nodes with deterministic node_id values."""

    template: Mapping[str, Any] = field(default_factory=_default_node_template)

    def build(self, *, assign_id: bool = True, **overrides: Any) -> dict[str, Any]:
        node: dict[str, Any] = deepcopy(dict(self.template))
        node.update(overrides)
        if assign_id and "node_id" not in overrides:
            node["node_id"] = compute_node_id(node)
        return node

    def build_without_id(self, **overrides: Any) -> dict[str, Any]:
        node = self.build(assign_id=False, **overrides)
        node.pop("node_id", None)
        return node


def make_node(**overrides: Any) -> dict[str, Any]:
    """Convenience helper returning a node with a computed ``node_id``."""

    return NodeFactory().build(**overrides)


__all__ = ["NodeFactory", "make_node"]
