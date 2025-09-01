from __future__ import annotations

import atexit
import json
import time
from pathlib import Path
from typing import Iterable, Dict

import networkx as nx

from .diff_service import NodeRepository, NodeRecord

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
                topic=record.topic,
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
                    topic=data.get("topic", ""),
                )
        return records

    def insert_sentinel(self, sentinel_id: str, node_ids: Iterable[str]) -> None:
        _GRAPH.add_node(sentinel_id, type="sentinel")
        for nid in node_ids:
            _GRAPH.add_edge(sentinel_id, nid)

    def get_queues_by_tag(
        self, tags: Iterable[str], interval: int, match_mode: str = "any"
    ) -> list[str]:
        tag_set = set(tags)
        queues: list[str] = []
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
                queues.append(data["topic"])
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
                    topic=data.get("topic", ""),
                )
        return None

    def mark_buffering(self, node_id: str, *, timestamp_ms: int | None = None) -> None:
        ts = timestamp_ms or int(time.time() * 1000)
        if _GRAPH.has_node(node_id):
            _GRAPH.nodes[node_id]["buffering_since"] = ts

    def clear_buffering(self, node_id: str) -> None:
        if _GRAPH.has_node(node_id):
            _GRAPH.nodes[node_id].pop("buffering_since", None)

    def get_buffering_nodes(self, older_than_ms: int) -> list[str]:
        result: list[str] = []
        for nid, data in _GRAPH.nodes(data=True):
            ts = data.get("buffering_since")
            if ts is not None and ts < older_than_ms:
                result.append(nid)
        return result


__all__ = ["MemoryNodeRepository"]
