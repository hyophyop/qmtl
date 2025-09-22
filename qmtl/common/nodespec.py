"""Utilities for canonical Node specification serialization."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

_PARAM_EXCLUDE_KEYS = {
    "world",
    "world_id",
    "world_ids",
    "execution_world",
    "execution_domain",
    "domain",
    "domains",
    "as_of",
    "partition",
    "dataset_fingerprint",
}


def _sorted_deps(node: Mapping[str, Any]) -> list[str]:
    deps = node.get("inputs") or node.get("dependencies") or []
    normalized: list[str] = []
    for dep in deps:
        if isinstance(dep, str):
            normalized.append(dep)
        elif dep is None:
            continue
        else:
            normalized.append(str(dep))
    return sorted(normalized)


def _canonicalize_params(value: Any) -> Any:
    if isinstance(value, Mapping):
        canonical: dict[str, Any] = {}
        for key in sorted(value.keys()):
            if key in _PARAM_EXCLUDE_KEYS:
                continue
            canonical[key] = _canonicalize_params(value[key])
        return canonical
    if isinstance(value, set):
        return sorted(_canonicalize_params(item) for item in value)
    if isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    ):
        return [_canonicalize_params(item) for item in value]
    if isinstance(value, (bytes, bytearray)):
        return value.decode()
    return value


def _canonical_params_blob(node: Mapping[str, Any]) -> str:
    params_source = node.get("params")
    if params_source is None:
        params_source = node.get("config")
    canonical = _canonicalize_params(params_source)
    return json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def serialize_nodespec(node: Mapping[str, Any]) -> bytes:
    node_type = str(node.get("node_type", ""))
    interval = int(node.get("interval") or 0)
    period = int(node.get("period") or 0)
    deps = _sorted_deps(node)
    schema_compat_id = str(node.get("schema_compat_id", ""))
    if not schema_compat_id:
        schema_compat_id = str(node.get("schema_id", ""))
    code_hash = str(node.get("code_hash", ""))
    params_blob = _canonical_params_blob(node)
    payload = "|".join(
        [
            node_type,
            str(interval),
            str(period),
            params_blob,
            ",".join(deps),
            schema_compat_id,
            code_hash,
        ]
    )
    return payload.encode()


__all__ = ["serialize_nodespec"]

