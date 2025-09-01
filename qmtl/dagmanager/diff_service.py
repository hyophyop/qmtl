from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, List, Dict, TYPE_CHECKING

try:  # optional high performance json
    import orjson as _json
except Exception:  # pragma: no cover - fallback
    import json as _json

_json_loads = _json.loads
import time
import asyncio

from .metrics import (
    observe_diff_duration,
    queue_create_error_total,
    sentinel_gap_count,
)
from .kafka_admin import KafkaAdmin
from .topic import TopicConfig, topic_name
from qmtl.common import AsyncCircuitBreaker
from .monitor import AckStatus

if TYPE_CHECKING:  # pragma: no cover - optional import for typing
    from neo4j import Driver


@dataclass
class DiffRequest:
    strategy_id: str
    dag_json: str


@dataclass
class DiffChunk:
    queue_map: Dict[str, str]
    sentinel_id: str
    buffering_nodes: List["BufferInstruction"] = field(default_factory=list)
    new_nodes: List["NodeInfo"] = field(default_factory=list)


@dataclass
class NodeInfo:
    node_id: str
    node_type: str
    code_hash: str
    schema_hash: str
    schema_id: str
    interval: int | None
    period: int | None
    tags: list[str]


@dataclass
class NodeRecord(NodeInfo):
    topic: str


@dataclass
class BufferInstruction(NodeInfo):
    lag: int


class NodeRepository:
    """Interface to fetch nodes and insert sentinels."""

    def get_nodes(
        self,
        node_ids: Iterable[str],
        *,
        breaker: AsyncCircuitBreaker | None = None,
    ) -> Dict[str, NodeRecord]:
        raise NotImplementedError

    def insert_sentinel(
        self,
        sentinel_id: str,
        node_ids: Iterable[str],
        *,
        breaker: AsyncCircuitBreaker | None = None,
    ) -> None:
        raise NotImplementedError

    def get_queues_by_tag(
        self,
        tags: Iterable[str],
        interval: int,
        match_mode: str = "any",
        *,
        breaker: AsyncCircuitBreaker | None = None,
    ) -> list[str]:
        """Return queue topics matching ``tags`` and ``interval``.

        ``match_mode`` determines whether all tags must match ("all") or any
        tag may match ("any").
        """
        raise NotImplementedError

    def get_node_by_queue(
        self,
        queue: str,
        *,
        breaker: AsyncCircuitBreaker | None = None,
    ) -> NodeRecord | None:
        """Return ``NodeRecord`` for the given queue topic, if any."""
        raise NotImplementedError

    # buffering -------------------------------------------------------------

    def mark_buffering(
        self,
        node_id: str,
        *,
        timestamp_ms: int | None = None,
        breaker: AsyncCircuitBreaker | None = None,
    ) -> None:
        """Record when ``node_id`` entered buffering mode."""
        raise NotImplementedError

    def clear_buffering(
        self,
        node_id: str,
        *,
        breaker: AsyncCircuitBreaker | None = None,
    ) -> None:
        """Remove buffering state from the given node."""
        raise NotImplementedError

    def get_buffering_nodes(
        self,
        older_than_ms: int,
        *,
        breaker: AsyncCircuitBreaker | None = None,
    ) -> list[str]:
        """Return node IDs buffering since before ``older_than_ms``."""
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
        dry_run: bool = False,
    ) -> str:
        raise NotImplementedError


class StreamSender:
    """Interface to send diff results as a stream."""

    def send(self, chunk: DiffChunk) -> None:
        raise NotImplementedError

    def wait_for_ack(self) -> AckStatus:
        """Block until the client acknowledges the last chunk."""
        raise NotImplementedError

    def ack(self, status: AckStatus = AckStatus.OK) -> None:
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
                schema_id=node_map[n].get("schema_id", ""),
                interval=node_map[n].get("interval"),
                period=node_map[n].get("period"),
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
    ) -> tuple[Dict[str, str], List[NodeInfo], List[NodeInfo]]:
        queue_map: Dict[str, str] = {}
        new_nodes: List[NodeInfo] = []
        buffering_nodes: List[NodeInfo] = []
        for n in nodes:
            rec = existing.get(n.node_id)
            if rec:
                if rec.code_hash == n.code_hash:
                    queue_map[n.node_id] = rec.topic
                    if rec.schema_hash != n.schema_hash:
                        buffering_nodes.append(n)
                    continue
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
        return queue_map, new_nodes, buffering_nodes

    def _buffer_instructions(self, nodes: Iterable[NodeInfo]) -> List[BufferInstruction]:
        """Create buffering instructions with lag equal to ``period``."""
        result: List[BufferInstruction] = []
        for n in nodes:
            lag = n.period or 0
            self.node_repo.mark_buffering(n.node_id)
            result.append(
                BufferInstruction(
                    node_id=n.node_id,
                    node_type=n.node_type,
                    code_hash=n.code_hash,
                    schema_hash=n.schema_hash,
                    schema_id=n.schema_id,
                    interval=n.interval,
                    period=n.period,
                    tags=list(n.tags),
                    lag=lag,
                )
            )
        return result

    # Step 4 ---------------------------------------------------------------
    def _insert_sentinel(self, sentinel_id: str, nodes: Iterable[NodeInfo]) -> None:
        self.node_repo.insert_sentinel(sentinel_id, [n.node_id for n in nodes])

    # Step 5 is handled inside _hash_compare via queue upsert --------------

    # Step 6 ---------------------------------------------------------------
    def _stream_send(
        self,
        queue_map: Dict[str, str],
        sentinel_id: str,
        new_nodes: List[NodeInfo],
        buffering_nodes: List[BufferInstruction],
    ) -> None:
        CHUNK_SIZE = 100
        total = max(len(new_nodes), len(buffering_nodes))
        if total == 0:
            # 그래도 최소 1개는 보내야 함 (empty chunk)
            self.stream_sender.send(
                DiffChunk(
                    queue_map=queue_map,
                    sentinel_id=sentinel_id,
                    new_nodes=[],
                    buffering_nodes=[],
                )
            )
            self.stream_sender.wait_for_ack()
            return
        for i in range(0, total, CHUNK_SIZE):
            chunk_new = new_nodes[i:i+CHUNK_SIZE]
            chunk_buf = buffering_nodes[i:i+CHUNK_SIZE]
            self.stream_sender.send(
                DiffChunk(
                    queue_map=queue_map,
                    sentinel_id=sentinel_id,
                    new_nodes=chunk_new,
                    buffering_nodes=chunk_buf,
                )
            )
            self.stream_sender.wait_for_ack()

    def diff(self, request: DiffRequest) -> DiffChunk:
        start = time.perf_counter()
        try:
            nodes = self._pre_scan(request.dag_json)
            existing = self._db_fetch([n.node_id for n in nodes])
            queue_map, new_nodes, buffering = self._hash_compare(nodes, existing)
            instructions = self._buffer_instructions(buffering)
            sentinel_id = f"{request.strategy_id}-sentinel"
            self._insert_sentinel(sentinel_id, new_nodes)
            if not new_nodes:
                sentinel_gap_count.inc()
                sentinel_gap_count._val = sentinel_gap_count._value.get()  # type: ignore[attr-defined]
            self._stream_send(queue_map, sentinel_id, new_nodes, instructions)
            return DiffChunk(
                queue_map=queue_map,
                sentinel_id=sentinel_id,
                new_nodes=new_nodes,
                buffering_nodes=instructions,
            )
        finally:
            duration_ms = (time.perf_counter() - start) * 1000
            observe_diff_duration(duration_ms)

    async def diff_async(self, request: DiffRequest) -> DiffChunk:
        return await asyncio.to_thread(self.diff, request)


class Neo4jNodeRepository(NodeRepository):
    """Neo4j-backed repository implementation."""

    def __init__(self, driver: 'Driver') -> None:
        self.driver = driver

    def _open_session(self, breaker: AsyncCircuitBreaker | None):
        """Return a driver session, passing ``breaker`` if supported."""
        try:
            return self.driver.session(breaker=breaker)
        except TypeError:
            return self.driver.session()

    def get_nodes(
        self,
        node_ids: Iterable[str],
        *,
        breaker: AsyncCircuitBreaker | None = None,
    ) -> Dict[str, NodeRecord]:
        if not node_ids:
            return {}
        query = (
            "MATCH (c:ComputeNode)-[:EMITS]->(q:Queue) "
            "WHERE c.node_id IN $ids "
            "RETURN c.node_id AS node_id, c.node_type AS node_type, "
            "c.code_hash AS code_hash, c.schema_hash AS schema_hash, "
            "q.topic AS topic, q.interval AS interval, c.period AS period, c.tags AS tags"
        )
        with self._open_session(breaker) as session:
            result = session.run(query, ids=list(node_ids))
            records: Dict[str, NodeRecord] = {}
            for r in result:
                records[r["node_id"]] = NodeRecord(
                    node_id=r["node_id"],
                    node_type=r.get("node_type", ""),
                    code_hash=r.get("code_hash"),
                    schema_hash=r.get("schema_hash"),
                    interval=r.get("interval"),
                    period=r.get("period"),
                    tags=list(r.get("tags", [])),
                    topic=r.get("topic"),
                )
            return records

    def insert_sentinel(
        self,
        sentinel_id: str,
        node_ids: Iterable[str],
        *,
        breaker: AsyncCircuitBreaker | None = None,
    ) -> None:
        if not node_ids:
            return
        query = (
            "CREATE (s:VersionSentinel {version: $sid, created_at: timestamp()}) "
            "WITH s UNWIND $ids AS nid MATCH (c:ComputeNode {node_id: nid}) "
            "MERGE (s)-[:HAS]->(c)"
        )
        with self._open_session(breaker) as session:
            session.run(query, sid=sentinel_id, ids=list(node_ids))

    def get_queues_by_tag(
        self,
        tags: Iterable[str],
        interval: int,
        match_mode: str = "any",
        *,
        breaker: AsyncCircuitBreaker | None = None,
    ) -> list[str]:
        if not tags:
            return []
        if match_mode == "all":
            cond = "all(t IN $tags WHERE t IN c.tags)"
        else:
            cond = "any(t IN c.tags WHERE t IN $tags)"
        query = (
            "MATCH (c:ComputeNode)-[:EMITS]->(q:Queue) "
            f"WHERE {cond} AND q.interval = $interval "
            "RETURN q.topic AS topic"
        )
        with self._open_session(breaker) as session:
            result = session.run(query, tags=list(tags), interval=interval)
            return [r.get("topic") for r in result]

    def get_node_by_queue(
        self,
        queue: str,
        *,
        breaker: AsyncCircuitBreaker | None = None,
    ) -> NodeRecord | None:
        query = (
            "MATCH (c:ComputeNode)-[:EMITS]->(q:Queue {topic: $queue}) "
            "RETURN c.node_id AS node_id, c.node_type AS node_type, "
            "c.code_hash AS code_hash, c.schema_hash AS schema_hash, "
            "q.topic AS topic, q.interval AS interval, c.period AS period, c.tags AS tags "
            "LIMIT 1"
        )
        with self._open_session(breaker) as session:
            result = session.run(query, queue=queue)
            record = result.single()
            if record is None:
                return None
            return NodeRecord(
                node_id=record["node_id"],
                node_type=record.get("node_type", ""),
                code_hash=record.get("code_hash"),
                schema_hash=record.get("schema_hash"),
                interval=record.get("interval"),
                period=record.get("period"),
                tags=list(record.get("tags", [])),
                topic=record.get("topic"),
            )

    # buffering -------------------------------------------------------------

    def mark_buffering(
        self,
        node_id: str,
        *,
        timestamp_ms: int | None = None,
        breaker: AsyncCircuitBreaker | None = None,
    ) -> None:
        query = (
            "MATCH (c:ComputeNode {node_id: $nid}) "
            "SET c.buffering_since = coalesce(c.buffering_since, $ts)"
        )
        ts = timestamp_ms or int(time.time() * 1000)
        with self._open_session(breaker) as session:
            session.run(query, nid=node_id, ts=ts)

    def clear_buffering(
        self,
        node_id: str,
        *,
        breaker: AsyncCircuitBreaker | None = None,
    ) -> None:
        query = (
            "MATCH (c:ComputeNode {node_id: $nid}) "
            "REMOVE c.buffering_since"
        )
        with self._open_session(breaker) as session:
            session.run(query, nid=node_id)

    def get_buffering_nodes(
        self,
        older_than_ms: int,
        *,
        breaker: AsyncCircuitBreaker | None = None,
    ) -> list[str]:
        query = (
            "MATCH (c:ComputeNode) WHERE c.buffering_since < $cutoff "
            "RETURN c.node_id AS node_id"
        )
        with self._open_session(breaker) as session:
            result = session.run(query, cutoff=older_than_ms)
            return [r.get("node_id") for r in result]


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
        dry_run: bool = False,
    ) -> str:
        existing = self.admin.client.list_topics().keys()
        topic = topic_name(
            asset,
            node_type,
            code_hash,
            version,
            dry_run=dry_run,
            existing=existing,
        )
        self.admin.create_topic_if_needed(topic, self.config)
        return topic

