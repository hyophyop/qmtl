from __future__ import annotations

import atexit
import json
import time
from pathlib import Path
from typing import Iterable, Dict

import networkx as nx

from qmtl.foundation.common import AsyncCircuitBreaker

from .models import NodeRecord
from .repository import NodeRepository

_GRAPH = nx.DiGraph()
_GRAPH_PATH: Path | None = None
_LOADED = False


def _load_graph(path: Path) -> None:
    global _GRAPH, _LOADED
    if path.exists():
        try:
            _GRAPH = nx.read_gpickle(path)
        except Exception:
            try:
                data = json.loads(path.read_text())
                _GRAPH = nx.node_link_graph(data, edges="edges")
            except Exception:
                _GRAPH = nx.DiGraph()
    _LOADED = True


def _save_graph() -> None:
    if _GRAPH_PATH is None:
        return
    try:
        nx.write_gpickle(_GRAPH, _GRAPH_PATH)
    except Exception:
        try:
            data = nx.node_link_data(_GRAPH, edges="edges")
            _GRAPH_PATH.write_text(json.dumps(data))
        except Exception:
            pass


class MemoryNodeRepository(NodeRepository):
    """In-memory repository using a global :class:`networkx.DiGraph`."""

    def __init__(self, path: str | None = None) -> None:
        global _GRAPH_PATH
        self._path = Path(path) if path else None
        if self._path is not None:
            if _GRAPH_PATH is None:
                _GRAPH_PATH = self._path
                _load_graph(self._path)
                atexit.register(_save_graph)
            elif not _LOADED:
                _load_graph(_GRAPH_PATH)

    # utility --------------------------------------------------------------
    def add_node(self, record: NodeRecord) -> None:
        _GRAPH.add_node(
            record.node_id,
            type="compute",
            node_type=record.node_type,
            code_hash=record.code_hash,
            schema_hash=record.schema_hash,
            schema_id=record.schema_id,
            interval=record.interval,
            period=record.period,
            tags=list(record.tags),
            bucket=record.bucket,
            topic=record.topic,
            compute_keys=list(record.compute_keys),
            **{"global": record.is_global},
        )

    # interface ------------------------------------------------------------
    def get_nodes(self, node_ids: Iterable[str]) -> Dict[str, NodeRecord]:
        records: Dict[str, NodeRecord] = {}
        for nid in node_ids:
            if _GRAPH.has_node(nid):
                data = _GRAPH.nodes[nid]
                if data.get("type") != "compute":
                    continue
                records[nid] = NodeRecord(
                    node_id=nid,
                    node_type=data.get("node_type", ""),
                    code_hash=data.get("code_hash", ""),
                    schema_hash=data.get("schema_hash", ""),
                    schema_id=data.get("schema_id", ""),
                    interval=data.get("interval"),
                    period=data.get("period"),
                    tags=list(data.get("tags", [])),
                    bucket=data.get("bucket"),
                    topic=data.get("topic", ""),
                    is_global=data.get("global", False),
                    compute_keys=tuple(data.get("compute_keys", []) or ()),
                )
        return records

    def insert_sentinel(
        self, sentinel_id: str, node_ids: Iterable[str], version: str
    ) -> None:
        _GRAPH.add_node(
            sentinel_id,
            type="sentinel",
            sentinel_id=sentinel_id,
            version=version,
            created_at=int(time.time() * 1000),
        )
        for nid in node_ids:
            _GRAPH.add_edge(sentinel_id, nid)

    def get_queues_by_tag(
        self, tags: Iterable[str], interval: int, match_mode: str = "any"
    ) -> list[dict[str, object]]:
        tag_set = set(tags)
        queues: list[dict[str, object]] = []
        for _, data in _GRAPH.nodes(data=True):
            if data.get("type") != "compute":
                continue
            if data.get("interval") != interval:
                continue
            node_tags = set(data.get("tags", []))
            if not tag_set:
                match = True
            elif match_mode == "all":
                match = tag_set.issubset(node_tags)
            else:
                match = bool(tag_set & node_tags)
            if match and "topic" in data:
                queues.append(
                    {
                        "queue": data["topic"],
                        "global": bool(data.get("global", False)),
                    }
                )
        return queues

    def get_node_by_queue(self, queue: str) -> NodeRecord | None:
        for nid, data in _GRAPH.nodes(data=True):
            if data.get("type") == "compute" and data.get("topic") == queue:
                return NodeRecord(
                    node_id=nid,
                    node_type=data.get("node_type", ""),
                    code_hash=data.get("code_hash", ""),
                    schema_hash=data.get("schema_hash", ""),
                    schema_id=data.get("schema_id", ""),
                    interval=data.get("interval"),
                    period=data.get("period"),
                    tags=list(data.get("tags", [])),
                    bucket=data.get("bucket"),
                    topic=data.get("topic", ""),
                    is_global=data.get("global", False),
                    compute_keys=tuple(data.get("compute_keys", []) or ()),
                )
        return None

    def mark_buffering(
        self,
        node_id: str,
        *,
        compute_key: str | None = None,
        timestamp_ms: int | None = None,
    ) -> None:
        ts = timestamp_ms or int(time.time() * 1000)
        if _GRAPH.has_node(node_id):
            data = _GRAPH.nodes[node_id]
            if compute_key:
                ctx = data.setdefault("buffering_since_ctx", {})
                if isinstance(ctx, dict):
                    ctx[compute_key] = ts
                else:
                    data["buffering_since_ctx"] = {compute_key: ts}
            else:
                data["buffering_since"] = ts

    def clear_buffering(
        self,
        node_id: str,
        *,
        compute_key: str | None = None,
    ) -> None:
        if not _GRAPH.has_node(node_id):
            return
        data = _GRAPH.nodes[node_id]
        if compute_key:
            ctx = data.get("buffering_since_ctx")
            if isinstance(ctx, dict):
                ctx.pop(compute_key, None)
                if not ctx:
                    data.pop("buffering_since_ctx", None)
        else:
            data.pop("buffering_since", None)
            ctx = data.get("buffering_since_ctx")
            if isinstance(ctx, dict):
                ctx.clear()

    def get_buffering_nodes(
        self,
        older_than_ms: int,
        *,
        compute_key: str | None = None,
    ) -> list[str]:
        result: list[str] = []
        for node_id, data in _GRAPH.nodes(data=True):
            if self._is_buffering(data, older_than_ms, compute_key):
                result.append(node_id)
        return result

    # compute-key bindings ------------------------------------------------

    def add_compute_binding(
        self,
        node_id: str,
        compute_key: str,
        *,
        breaker: AsyncCircuitBreaker | None = None,
    ) -> None:
        if not compute_key:
            return
        if not _GRAPH.has_node(node_id):
            _GRAPH.add_node(
                node_id,
                type="compute",
                compute_keys=[compute_key],
            )
            return
        data = _GRAPH.nodes[node_id]
        keys = data.get("compute_keys")
        if isinstance(keys, list):
            if compute_key not in keys:
                keys.append(compute_key)
                data["compute_keys"] = keys
        elif isinstance(keys, (set, tuple)):
            merged = set(keys)
            merged.add(compute_key)
            data["compute_keys"] = list(merged)
        else:
            data["compute_keys"] = [compute_key]

    def _is_buffering(
        self, data: dict[str, Any], older_than_ms: int, compute_key: str | None
    ) -> bool:
        ts = data.get("buffering_since")
        if compute_key:
            return self._has_buffering_ctx_ts(data, compute_key, older_than_ms)
        if self._any_buffering_ctx(data, older_than_ms):
            return True
        return bool(ts is not None and ts < older_than_ms)

    def _has_buffering_ctx_ts(
        self, data: dict[str, Any], compute_key: str, older_than_ms: int
    ) -> bool:
        ctx = data.get("buffering_since_ctx")
        if not isinstance(ctx, dict):
            return False
        ctx_ts = ctx.get(compute_key)
        return bool(ctx_ts is not None and ctx_ts < older_than_ms)

    def _any_buffering_ctx(self, data: dict[str, Any], older_than_ms: int) -> bool:
        ctx = data.get("buffering_since_ctx")
        if not isinstance(ctx, dict):
            return False
        return any(ts is not None and ts < older_than_ms for ts in ctx.values())


__all__ = ["MemoryNodeRepository"]
