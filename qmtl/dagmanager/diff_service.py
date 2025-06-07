from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Iterable, List, Dict
import time

from .metrics import observe_diff_duration, queue_create_error_total


@dataclass
class DiffRequest:
    strategy_id: str
    dag_json: str


@dataclass
class DiffChunk:
    queue_map: Dict[str, str]
    sentinel_id: str


@dataclass
class NodeInfo:
    node_id: str
    code_hash: str
    schema_hash: str


@dataclass
class NodeRecord(NodeInfo):
    topic: str


class NodeRepository:
    """Interface to fetch nodes and insert sentinels."""

    def get_nodes(self, node_ids: Iterable[str]) -> Dict[str, NodeRecord]:
        raise NotImplementedError

    def insert_sentinel(self, sentinel_id: str, node_ids: Iterable[str]) -> None:
        raise NotImplementedError


class QueueManager:
    """Interface to create or update queues."""

    def upsert(self, node_id: str) -> str:
        raise NotImplementedError


class StreamSender:
    """Interface to send diff results as a stream."""

    def send(self, chunk: DiffChunk) -> None:
        raise NotImplementedError


class DiffService:
    """Process :class:`DiffRequest` following the documented steps."""

    def __init__(
        self,
        node_repo: NodeRepository,
        queue_manager: QueueManager,
        stream_sender: StreamSender,
    ) -> None:
        self.node_repo = node_repo
        self.queue_manager = queue_manager
        self.stream_sender = stream_sender

    # Step 1 ---------------------------------------------------------------
    def _pre_scan(self, dag_json: str) -> List[NodeInfo]:
        data = json.loads(dag_json)
        nodes = []
        for n in data.get("nodes", []):
            nodes.append(
                NodeInfo(
                    node_id=n["node_id"],
                    code_hash=n["code_hash"],
                    schema_hash=n["schema_hash"],
                )
            )
        return nodes

    # Step 2 ---------------------------------------------------------------
    def _db_fetch(self, node_ids: Iterable[str]) -> Dict[str, NodeRecord]:
        return self.node_repo.get_nodes(node_ids)

    # Step 3 ---------------------------------------------------------------
    def _hash_compare(
        self, nodes: Iterable[NodeInfo], existing: Dict[str, NodeRecord]
    ) -> tuple[Dict[str, str], List[NodeInfo]]:
        queue_map: Dict[str, str] = {}
        new_nodes: List[NodeInfo] = []
        for n in nodes:
            rec = existing.get(n.node_id)
            if rec and rec.code_hash == n.code_hash and rec.schema_hash == n.schema_hash:
                queue_map[n.node_id] = rec.topic
            else:
                try:
                    topic = self.queue_manager.upsert(n.node_id)
                except Exception:
                    queue_create_error_total.inc()
                    queue_create_error_total._val = queue_create_error_total._value.get()  # type: ignore[attr-defined]
                    raise
                queue_map[n.node_id] = topic
                new_nodes.append(n)
        return queue_map, new_nodes

    # Step 4 ---------------------------------------------------------------
    def _insert_sentinel(self, sentinel_id: str, nodes: Iterable[NodeInfo]) -> None:
        self.node_repo.insert_sentinel(sentinel_id, [n.node_id for n in nodes])

    # Step 5 is handled inside _hash_compare via queue upsert --------------

    # Step 6 ---------------------------------------------------------------
    def _stream_send(self, queue_map: Dict[str, str], sentinel_id: str) -> None:
        self.stream_sender.send(DiffChunk(queue_map=queue_map, sentinel_id=sentinel_id))

    def diff(self, request: DiffRequest) -> DiffChunk:
        start = time.perf_counter()
        try:
            nodes = self._pre_scan(request.dag_json)
            existing = self._db_fetch([n.node_id for n in nodes])
            queue_map, new_nodes = self._hash_compare(nodes, existing)
            sentinel_id = f"{request.strategy_id}-sentinel"
            self._insert_sentinel(sentinel_id, new_nodes)
            self._stream_send(queue_map, sentinel_id)
            return DiffChunk(queue_map=queue_map, sentinel_id=sentinel_id)
        finally:
            duration_ms = (time.perf_counter() - start) * 1000
            observe_diff_duration(duration_ms)
