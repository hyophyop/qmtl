"""Factories for canonical node payloads used across tests."""

from __future__ import annotations

import json
from typing import Any, Iterable, Mapping, Sequence

from qmtl.common import compute_node_id, crc32_of_list
from qmtl.common.nodespec import serialize_nodespec


def _normalize_dependencies(deps: Sequence[Any] | None) -> list[str]:
    if not deps:
        return []
    normalized: list[str] = []
    for dep in deps:
        if dep in (None, ""):
            continue
        if isinstance(dep, str):
            normalized.append(dep)
        else:
            normalized.append(str(dep))
    return sorted(normalized)


def _canonical_params(payload: Mapping[str, Any]) -> Any:
    params_source = payload.get("params")
    if params_source is None:
        params_source = payload.get("config")
    spec = {
        "node_type": payload.get("node_type", ""),
        "interval": int(payload.get("interval") or 0),
        "period": int(payload.get("period") or 0),
        "params": params_source,
        "dependencies": payload.get("dependencies", []),
        "schema_compat_id": payload.get("schema_compat_id")
        or payload.get("schema_id")
        or "",
        "code_hash": payload.get("code_hash", ""),
    }
    params_blob = serialize_nodespec(spec).decode().split("|", 6)[3]
    if not params_blob or params_blob == "null":
        return {}
    canonical = json.loads(params_blob)
    if canonical is None:
        return {}
    return canonical


def canonical_node_payload(
    *,
    node_type: str,
    interval: int = 0,
    period: int = 0,
    params: Mapping[str, Any] | None = None,
    config: Mapping[str, Any] | None = None,
    dependencies: Sequence[Any] | None = None,
    inputs: Sequence[Any] | None = None,
    schema_hash: str = "schema",
    schema_compat_id: str | None = None,
    code_hash: str = "code",
    config_hash: str = "cfg",
    include_node_id: bool = True,
    extras: Mapping[str, Any] | None = None,
    **overrides: Any,
) -> dict[str, Any]:
    """Build a canonical node payload for gateway and SDK tests."""

    payload: dict[str, Any] = {
        "node_type": node_type,
        "interval": interval,
        "period": period,
        "params": params if params is not None else {},
        "dependencies": list(dependencies or []),
        "schema_hash": schema_hash,
        "schema_compat_id": (schema_compat_id or f"{schema_hash}-major"),
        "code_hash": code_hash,
        "config_hash": config_hash,
    }
    if config is not None:
        payload["config"] = config
    if inputs is not None:
        payload["inputs"] = list(inputs)
    if extras:
        payload.update(extras)
    payload.update(overrides)
    payload["dependencies"] = _normalize_dependencies(payload.get("dependencies"))
    if "inputs" in payload:
        payload["inputs"] = _normalize_dependencies(payload.get("inputs"))
    payload["params"] = _canonical_params(payload)
    spec = {
        "node_type": payload["node_type"],
        "interval": int(payload.get("interval") or 0),
        "period": int(payload.get("period") or 0),
        "params": payload.get("params"),
        "dependencies": payload.get("dependencies", []),
        "schema_compat_id": payload.get("schema_compat_id")
        or payload.get("schema_id", ""),
        "code_hash": payload.get("code_hash", ""),
    }
    if include_node_id:
        payload.setdefault("node_id", compute_node_id(spec))
    return payload


def tag_query_node_payload(
    *,
    tags: Sequence[str],
    match_mode: str = "any",
    interval: int = 60,
    period: int = 0,
    schema_hash: str = "tag-schema",
    schema_compat_id: str | None = None,
    code_hash: str = "tag-code",
    config_hash: str = "cfg",
    dependencies: Sequence[Any] | None = None,
    inputs: Sequence[Any] | None = None,
    params: Mapping[str, Any] | None = None,
    include_node_id: bool = True,
    **overrides: Any,
) -> dict[str, Any]:
    """Build a canonical TagQuery node payload."""

    tag_list = list(tags)
    resolved_params = params if params is not None else {"tags": tag_list, "match_mode": match_mode}
    extras = {"tags": tag_list}
    return canonical_node_payload(
        node_type="TagQueryNode",
        interval=interval,
        period=period,
        params=resolved_params,
        dependencies=dependencies,
        inputs=inputs,
        schema_hash=schema_hash,
        schema_compat_id=schema_compat_id,
        code_hash=code_hash,
        config_hash=config_hash,
        include_node_id=include_node_id,
        extras=extras,
        **overrides,
    )


def indicator_node_payload(
    *,
    interval: int = 60,
    period: int = 5,
    window: int = 5,
    schema_hash: str = "indicator-schema",
    schema_compat_id: str | None = None,
    code_hash: str = "indicator-code",
    config_hash: str = "cfg",
    dependencies: Sequence[Any] | None = None,
    params: Mapping[str, Any] | None = None,
    include_node_id: bool = True,
    **overrides: Any,
) -> dict[str, Any]:
    """Build a canonical Indicator node payload."""

    resolved_params = params if params is not None else {"window": window}
    return canonical_node_payload(
        node_type="IndicatorNode",
        interval=interval,
        period=period,
        params=resolved_params,
        dependencies=dependencies,
        schema_hash=schema_hash,
        schema_compat_id=schema_compat_id,
        code_hash=code_hash,
        config_hash=config_hash,
        include_node_id=include_node_id,
        **overrides,
    )


def canonical_dag(*nodes: Mapping[str, Any]) -> dict[str, Any]:
    """Return a canonical DAG wrapper for ``nodes``."""

    return {"nodes": [dict(node) for node in nodes]}


def node_ids_crc32(nodes: Iterable[Mapping[str, Any]] | None) -> int:
    """Compute CRC32 over the node identifiers present in ``nodes``."""

    if not nodes:
        return 0
    return crc32_of_list(node.get("node_id") for node in nodes if node.get("node_id"))


__all__ = [
    "canonical_dag",
    "canonical_node_payload",
    "indicator_node_payload",
    "node_ids_crc32",
    "tag_query_node_payload",
]
