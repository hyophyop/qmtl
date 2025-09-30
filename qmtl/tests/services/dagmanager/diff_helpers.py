"""Utility helpers shared across diff service tests."""
from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

from qmtl.services.dagmanager import metrics
from qmtl.services.dagmanager.diff_service import DiffRequest
from qmtl.services.dagmanager.kafka_admin import compute_key, partition_key


def build_dag(nodes: Iterable[dict[str, Any]], meta: dict[str, Any] | None = None) -> str:
    payload: dict[str, Any] = {"nodes": list(nodes)}
    if meta:
        payload["meta"] = meta
    return json.dumps(payload)


def dag_node(
    node_id: str,
    *,
    node_type: str = "N",
    code_hash: str,
    schema_hash: str,
    **extra: Any,
) -> dict[str, Any]:
    node = {
        "node_id": node_id,
        "node_type": node_type,
        "code_hash": code_hash,
        "schema_hash": schema_hash,
    }
    node.update(extra)
    return node


def make_diff_request(
    *,
    strategy_id: str = "s",
    nodes: Iterable[dict[str, Any]] | None = None,
    meta: dict[str, Any] | None = None,
) -> DiffRequest:
    return DiffRequest(strategy_id=strategy_id, dag_json=build_dag(nodes or [], meta))


def partition_with_context(
    node_id: str,
    interval: int | None = None,
    bucket: int | None = None,
    **context: Any,
) -> str:
    return partition_key(
        node_id,
        interval,
        bucket,
        compute_key=compute_key(node_id, **context),
    )


def reset_diff_metrics():
    metrics.reset_metrics()


__all__ = [
    "build_dag",
    "dag_node",
    "make_diff_request",
    "partition_with_context",
    "reset_diff_metrics",
]
