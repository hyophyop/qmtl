"""Utility helpers for execution-layer pipeline nodes."""

from __future__ import annotations

import asyncio
from typing import Any, Callable, Mapping, MutableMapping

from qmtl.dagmanager.kafka_admin import compute_key
from qmtl.sdk.node import CacheView, Node, ProcessingNode
from qmtl.sdk.watermark import WatermarkGate


CacheEntry = tuple[int, Any]


def latest_entry(view: CacheView, node: Node) -> CacheEntry | None:
    """Return the most recent cache entry for ``node`` if available."""

    data = view[node][node.interval]
    if not data:
        return None
    return data[-1]


def normalise_watermark_gate(
    gate: WatermarkGate | Mapping[str, Any] | bool | None,
) -> WatermarkGate:
    """Coerce arbitrary watermark gate configuration into ``WatermarkGate``."""

    if isinstance(gate, WatermarkGate):
        return gate
    if gate is None or gate is False:
        return WatermarkGate(enabled=False)
    if gate is True:
        return WatermarkGate(enabled=True)
    if isinstance(gate, Mapping):
        return WatermarkGate(**gate)
    raise TypeError("Unsupported watermark gate configuration")


def safe_call(func: Callable[..., Any] | None, *args: Any, **kwargs: Any) -> Any | None:
    """Call ``func`` and suppress unexpected exceptions."""

    if func is None:
        return None
    try:
        return func(*args, **kwargs)
    except Exception:
        return None


def commit_log_key_hint(node: ProcessingNode, upstream: Node) -> str | None:
    """Compute a commit-log key hint using metadata from the node graph."""

    def _ctx(name: str) -> str | None:
        for source in (node, upstream):
            value = getattr(source, name, None)
            if value is not None:
                return str(value)
        return None

    return compute_key(
        node.node_id,
        world_id=_ctx("world_id"),
        execution_domain=_ctx("execution_domain"),
        as_of=_ctx("as_of"),
        partition=_ctx("partition"),
        dataset_fingerprint=_ctx("dataset_fingerprint"),
    )


def publish_commit_log(
    writer: Any,
    node: ProcessingNode,
    upstream: Node,
    ts: int,
    interval: int,
    order: MutableMapping[str, Any],
) -> None:
    """Publish an order payload to the commit log writer if configured."""

    if writer is None:
        return
    try:
        key_hint = commit_log_key_hint(node, upstream)
        coro = writer.publish_bucket(
            ts,
            interval,
            [(node.node_id, "", order, key_hint)],
        )
        try:
            asyncio.get_running_loop().create_task(coro)
        except RuntimeError:
            asyncio.run(coro)
    except Exception:
        pass
