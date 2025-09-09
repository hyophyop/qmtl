from __future__ import annotations

"""Canonical NodeSpec serializer and NodeID helper (scaffold).

This follows the spirit of the architecture spec by capturing deterministic
fields and a sorted dependency list from a DAG node dictionary.
"""

from typing import Any, Iterable
from blake3 import blake3


def _sorted_deps(node: dict) -> list[str]:
    deps = node.get("inputs") or node.get("dependencies") or []
    return sorted([str(d) for d in deps])


def serialize_nodespec(node: dict[str, Any]) -> bytes:
    node_type = str(node.get("node_type", ""))
    interval = int(node.get("interval") or 0)
    period = int(node.get("period") or 0)
    params = node.get("params") or node.get("config") or {}
    # Normalize params: flatten simple key/values and sort by key
    items = []
    if isinstance(params, dict):
        for k in sorted(params.keys()):
            v = params[k]
            items.append(f"{k}={v}")
    deps = _sorted_deps(node)
    schema_compat_id = str(node.get("schema_id", ""))
    code_hash = str(node.get("code_hash", ""))
    payload = "|".join(
        [
            node_type,
            str(interval),
            str(period),
            ";".join(items),
            ",".join(deps),
            schema_compat_id,
            code_hash,
        ]
    )
    return payload.encode()


def canonical_node_id(node: dict[str, Any]) -> str:
    data = serialize_nodespec(node)
    return f"blake3:{blake3(data).hexdigest()}"


__all__ = ["serialize_nodespec", "canonical_node_id"]

