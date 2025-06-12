from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, List, Dict, TYPE_CHECKING

try:  # optional high performance json
    import orjson as _json
except Exception:  # pragma: no cover - fallback
    import json as _json

_json_loads = _json.loads
import time

from .metrics import (
    observe_diff_duration,
    queue_create_error_total,
    sentinel_gap_count,
)
from .kafka_admin import KafkaAdmin
from .topic import TopicConfig, topic_name

if TYPE_CHECKING:  # pragma: no cover - optional import for typing
    from neo4j import Driver


@dataclass
class DiffRequest:
    strategy_id: str
    dag_json: str


@dataclass
class DiffChunk:
    chunk_id: int
    queue_map: Dict[str, str]
    sentinel_id: str
    new_nodes: List["NodeInfo"] = field(default_factory=list)


@dataclass
class NodeInfo:
    node_id: str
    node_type: str
    code_hash: str
    schema_hash: str
    interval: int | None
    tags: list[str]


@dataclass
class NodeRecord(NodeInfo):
    topic: str


class NodeRepository:
    """Interface to fetch nodes and insert sentinels."""

    def get_nodes(self, node_ids: Iterable[str]) -> Dict[str, NodeRecord]:
        raise NotImplementedError

    def insert_sentinel(self, sentinel_id: str, node_ids: Iterable[str]) -> None:
        raise NotImplementedError

    def get_queues_by_tag(self, tags: Iterable[str], interval: int) -> list[str]:
        """Return queue topics matching ``tags`` and ``interval``."""
        raise NotImplementedError


class QueueManager:
    """Interface to create or update queues."""

    def upsert(
        self,
        asset: str,
        node_type: str,
        code_hash: str,
        version: str,
        *,
        dryrun: bool = False,
    ) -> str:
        raise NotImplementedError


class StreamSender:
    """Interface to send diff results as a stream."""

    def send(self, chunk: DiffChunk) -> None:
        raise NotImplementedError

    def wait_for_ack(self) -> None:
        """Block until the client acknowledges the last chunk."""
        raise NotImplementedError

    def ack(self) -> None:
        """Signal that the last chunk was received."""
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
        """Parse DAG JSON and return nodes in topological order."""
        data = _json_loads(dag_json)

        node_map = {n["node_id"]: n for n in data.get("nodes", [])}
        deps: Dict[str, set[str]] = {
            nid: set(node_map[nid].get("inputs", [])) for nid in node_map
        }

        ordered: List[str] = []
        ready = [nid for nid, d in deps.items() if not d]
        while ready:
            nid = ready.pop(0)
            ordered.append(nid)
            for other, d in deps.items():
                if nid in d:
                    d.remove(nid)
                    if not d:
                        ready.append(other)

        if len(ordered) != len(node_map):  # cycle fallback to given order
            ordered = list(node_map.keys())

        return [
            NodeInfo(
                node_id=node_map[n]["node_id"],
                node_type=node_map[n].get("node_type", ""),
                code_hash=node_map[n]["code_hash"],
                schema_hash=node_map[n]["schema_hash"],
                interval=node_map[n].get("interval"),
                tags=list(node_map[n].get("tags", [])),
            )
            for n in ordered
        ]

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
                    topic = self.queue_manager.upsert(
                        "asset",
                        n.node_type,
                        n.code_hash,
                        "v1",
                    )
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
    def _stream_send(
        self, queue_map: Dict[str, str], sentinel_id: str, new_nodes: List[NodeInfo]
    ) -> None:
        items = list(queue_map.items())
        start = 0
        chunk_id = 0
        first = True
        while start < len(items):
            size = 0
            chunk_items: Dict[str, str] = {}
            count = 0
            while start < len(items) and count < 100 and size < 1024 * 1024:
                k, v = items[start]
                size += len(k.encode()) + len(v.encode())
                chunk_items[k] = v
                start += 1
                count += 1
            self.stream_sender.send(
                DiffChunk(
                    chunk_id=chunk_id,
                    queue_map=chunk_items,
                    sentinel_id=sentinel_id,
                    new_nodes=list(new_nodes) if first else [],
                )
            )
            self.stream_sender.wait_for_ack()
            chunk_id += 1
            first = False

    def diff(self, request: DiffRequest) -> DiffChunk:
        start = time.perf_counter()
        try:
            nodes = self._pre_scan(request.dag_json)
            existing = self._db_fetch([n.node_id for n in nodes])
            queue_map, new_nodes = self._hash_compare(nodes, existing)
            sentinel_id = f"{request.strategy_id}-sentinel"
            self._insert_sentinel(sentinel_id, new_nodes)
            if not new_nodes:
                sentinel_gap_count.inc()
                sentinel_gap_count._val = sentinel_gap_count._value.get()  # type: ignore[attr-defined]
            self._stream_send(queue_map, sentinel_id, new_nodes)
            return DiffChunk(chunk_id=0, queue_map=queue_map, sentinel_id=sentinel_id, new_nodes=new_nodes)
        finally:
            duration_ms = (time.perf_counter() - start) * 1000
            observe_diff_duration(duration_ms)


class Neo4jNodeRepository(NodeRepository):
    """Neo4j-backed repository implementation."""

    def __init__(self, driver: 'Driver') -> None:
        self.driver = driver

    def get_nodes(self, node_ids: Iterable[str]) -> Dict[str, NodeRecord]:
        if not node_ids:
            return {}
        query = (
            "MATCH (c:ComputeNode)-[:EMITS]->(q:Queue) "
            "WHERE c.node_id IN $ids "
            "RETURN c.node_id AS node_id, c.node_type AS node_type, "
            "c.code_hash AS code_hash, c.schema_hash AS schema_hash, "
            "q.topic AS topic, q.interval AS interval, c.tags AS tags"
        )
        with self.driver.session() as session:
            result = session.run(query, ids=list(node_ids))
            records: Dict[str, NodeRecord] = {}
            for r in result:
                records[r["node_id"]] = NodeRecord(
                    node_id=r["node_id"],
                    node_type=r.get("node_type", ""),
                    code_hash=r.get("code_hash"),
                    schema_hash=r.get("schema_hash"),
                    interval=r.get("interval"),
                    tags=list(r.get("tags", [])),
                    topic=r.get("topic"),
                )
            return records

    def insert_sentinel(self, sentinel_id: str, node_ids: Iterable[str]) -> None:
        if not node_ids:
            return
        query = (
            "CREATE (s:VersionSentinel {version: $sid, created_at: timestamp()}) "
            "WITH s UNWIND $ids AS nid MATCH (c:ComputeNode {node_id: nid}) "
            "MERGE (s)-[:HAS]->(c)"
        )
        with self.driver.session() as session:
            session.run(query, sid=sentinel_id, ids=list(node_ids))

    def get_queues_by_tag(self, tags: Iterable[str], interval: int) -> list[str]:
        if not tags:
            return []
        query = (
            "MATCH (c:ComputeNode)-[:EMITS]->(q:Queue) "
            "WHERE any(t IN c.tags WHERE t IN $tags) AND q.interval = $interval "
            "RETURN q.topic AS topic"
        )
        with self.driver.session() as session:
            result = session.run(query, tags=list(tags), interval=interval)
            return [r.get("topic") for r in result]


class KafkaQueueManager(QueueManager):
    """Queue manager using :class:`KafkaAdmin`."""

    def __init__(self, admin: KafkaAdmin, config: TopicConfig | None = None) -> None:
        self.admin = admin
        self.config = config or TopicConfig(1, 1, 24 * 60 * 60 * 1000)

    def upsert(
        self,
        asset: str,
        node_type: str,
        code_hash: str,
        version: str,
        *,
        dryrun: bool = False,
    ) -> str:
        existing = self.admin.client.list_topics().keys()
        topic = topic_name(
            asset,
            node_type,
            code_hash,
            version,
            dryrun=dryrun,
            existing=existing,
        )
        self.admin.create_topic_if_needed(topic, self.config)
        return topic

