from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Iterable, List, Dict, TYPE_CHECKING

try:  # optional high performance json
    import orjson as _json
except Exception:  # pragma: no cover - fallback
    import json as _json

_json_loads = _json.loads
import time
import asyncio


def _normalize_version(raw: object, default: str = "v1") -> str:
    """Normalize version strings for topic naming.

    Falls back to ``default`` when ``raw`` is falsy or not a primitive.
    Invalid characters are replaced with ``-`` and leading/trailing
    punctuation is stripped to keep Kafka topic suffixes tidy.
    """

    if isinstance(raw, (int, float)):
        value = str(raw)
    elif isinstance(raw, str):
        value = raw.strip()
    else:
        value = ""
    if not value:
        return default
    cleaned = []
    for ch in value:
        if ch.isalnum() or ch in {"-", "_", "."}:
            cleaned.append(ch)
        elif ch.isspace():
            cleaned.append("-")
        else:
            cleaned.append("-")
    result = "".join(cleaned).strip("-_.")
    return result or default


def _stringify(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        return str(value)
    return str(value).strip()


def _normalize_execution_domain(raw: object) -> str:
    value = _stringify(raw)
    return value.lower() or "live"


from .metrics import (
    observe_diff_duration,
    queue_create_error_total,
    sentinel_gap_count,
    diff_requests_total,
    diff_failures_total,
)
from .kafka_admin import KafkaAdmin, partition_key, compute_key
from .topic import (
    TopicConfig,
    topic_name,
    get_config,
    topic_namespace_enabled,
    normalize_namespace,
    build_namespace,
    ensure_namespace,
)
from qmtl.common import AsyncCircuitBreaker
from qmtl.common.metrics_shared import observe_cross_context_cache_hit
from .monitor import AckStatus

if TYPE_CHECKING:  # pragma: no cover - optional import for typing
    from neo4j import Driver


@dataclass
class DiffRequest:
    strategy_id: str
    dag_json: str
    world_id: str | None = None
    execution_domain: str | None = None
    as_of: str | None = None
    partition: str | None = None
    dataset_fingerprint: str | None = None


@dataclass(frozen=True)
class ComputeContext:
    world_id: str = ""
    execution_domain: str = "live"
    as_of: str = ""
    partition: str = ""
    dataset_fingerprint: str = ""

    def label_values(self) -> tuple[str, str]:
        return (
            self.world_id or "",
            self.execution_domain or "",
        )


@dataclass
class _CachedBinding:
    topic: str
    code_hash: str
    schema_hash: str


@dataclass
class DiffChunk:
    queue_map: Dict[str, str]
    sentinel_id: str
    version: str
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
    bucket: int | None = None
    is_global: bool = False
    compute_key: str | None = field(default=None, init=False)


@dataclass
class NodeRecord(NodeInfo):
    topic: str = ""


@dataclass
class BufferInstruction(NodeInfo):
    lag: int = 0


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
        version: str,
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
    ) -> list[dict[str, object]]:
        """Return queue descriptors matching ``tags`` and ``interval``.

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
        compute_key: str | None = None,
        timestamp_ms: int | None = None,
        breaker: AsyncCircuitBreaker | None = None,
    ) -> None:
        """Record when ``node_id`` entered buffering mode."""
        raise NotImplementedError

    def clear_buffering(
        self,
        node_id: str,
        *,
        compute_key: str | None = None,
        breaker: AsyncCircuitBreaker | None = None,
    ) -> None:
        """Remove buffering state from the given node."""
        raise NotImplementedError

    def get_buffering_nodes(
        self,
        older_than_ms: int,
        *,
        compute_key: str | None = None,
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
        namespace: object | None = None,
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
        self._bindings: Dict[str, Dict[str, _CachedBinding]] = {}

    # Step 1 ---------------------------------------------------------------
    def _pre_scan(
        self, dag_json: str
    ) -> tuple[List[NodeInfo], str, ComputeContext, str | None]:
        """Parse DAG JSON and return nodes, version, compute context, namespace."""
        data = _json_loads(dag_json)

        raw_nodes = data.get("nodes", []) or []
        meta_obj = data.get("meta")
        meta = meta_obj if isinstance(meta_obj, dict) else {}
        sentinel_version: str | None = None
        filtered_nodes: list[dict] = []
        context = self._extract_compute_context(data)
        namespace: str | None = None
        if topic_namespace_enabled():
            raw_namespace = meta.get("topic_namespace")
            normalized = normalize_namespace(raw_namespace)
            if normalized:
                namespace = normalized
            else:
                world_for_ns = context.world_id or _stringify(
                    meta.get("world") or meta.get("world_id")
                )
                domain_for_ns = context.execution_domain or _normalize_execution_domain(
                    meta.get("execution_domain") or meta.get("domain")
                )
                if world_for_ns:
                    namespace = build_namespace(world_for_ns, domain_for_ns)
        for entry in raw_nodes:
            if not isinstance(entry, dict):
                continue
            node_type = str(entry.get("node_type", ""))
            if node_type == "VersionSentinel":
                if sentinel_version is None:
                    for key in ("version", "strategy_version", "build_version"):
                        if key in entry:
                            sentinel_version = _normalize_version(entry.get(key))
                            if sentinel_version:
                                break
                    if not sentinel_version:
                        sentinel_version = _normalize_version(entry.get("node_id"))
                continue
            filtered_nodes.append(entry)

        node_map = {n["node_id"]: n for n in filtered_nodes if "node_id" in n}
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

        nodes = [
            NodeInfo(
                node_id=node_map[n]["node_id"],
                node_type=node_map[n].get("node_type", ""),
                code_hash=node_map[n]["code_hash"],
                schema_hash=node_map[n]["schema_hash"],
                schema_id=node_map[n].get("schema_id", ""),
                interval=node_map[n].get("interval"),
                period=node_map[n].get("period"),
                tags=list(node_map[n].get("tags", [])),
                bucket=node_map[n].get("bucket"),
            )
            for n in ordered
        ]
        for node in nodes:
            node.compute_key = compute_key(
                node.node_id,
                world_id=context.world_id or None,
                execution_domain=context.execution_domain or None,
                as_of=context.as_of or None,
                partition=context.partition or None,
                dataset_fingerprint=context.dataset_fingerprint or None,
            )
        if sentinel_version:
            version = sentinel_version
        else:
            version = _normalize_version(
                data.get("strategy_version")
                or data.get("version")
                or meta.get("version")
                or meta.get("strategy_version")
                or meta.get("build_version")
            )
        return nodes, version, context, namespace

    # Step 2 ---------------------------------------------------------------
    def _db_fetch(self, node_ids: Iterable[str]) -> Dict[str, NodeRecord]:
        return self.node_repo.get_nodes(node_ids)

    def _extract_compute_context(self, payload: dict) -> ComputeContext:
        meta = payload.get("meta") or {}
        ctx = payload.get("compute_context")
        if not isinstance(ctx, dict):
            ctx = meta.get("compute_context")
        if not isinstance(ctx, dict):
            ctx = {}
        return ComputeContext(
            world_id=_stringify(ctx.get("world_id")),
            execution_domain=_normalize_execution_domain(ctx.get("execution_domain")),
            as_of=_stringify(ctx.get("as_of")),
            partition=_stringify(ctx.get("partition")),
            dataset_fingerprint=_stringify(
                ctx.get("dataset_fingerprint") or meta.get("dataset_fingerprint")
            ),
        )

    def _record_cross_context_hit(
        self, node: NodeInfo, context: ComputeContext
    ) -> None:
        observe_cross_context_cache_hit(
            node.node_id,
            context.world_id or "",
            context.execution_domain or "",
            as_of=context.as_of or None,
            partition=context.partition or None,
        )

    # Step 3 ---------------------------------------------------------------
    def _hash_compare(
        self,
        nodes: Iterable[NodeInfo],
        existing: Dict[str, NodeRecord],
        version: str,
        compute_context: ComputeContext,
        *,
        namespace: object | None = None,
    ) -> tuple[Dict[str, str], List[NodeInfo], List[NodeInfo]]:
        queue_map: Dict[str, str] = {}
        new_nodes: List[NodeInfo] = []
        buffering_nodes: List[NodeInfo] = []

        def _asset_from_tags(tags: list[str]) -> str:
            # Prefer a short, stable asset name derived from tags
            for t in tags:
                if not t:
                    continue
                s = ''.join(ch for ch in str(t).lower() if ch.isalnum() or ch in ('_', '-'))
                if s:
                    return s
            return 'asset'

        def _ensure_topic_namespace(topic: str, node: NodeInfo) -> str:
            if not namespace:
                return topic
            namespaced = ensure_namespace(topic, namespace)
            if namespaced != topic:
                try:
                    return self.queue_manager.upsert(
                        _asset_from_tags(node.tags),
                        node.node_type,
                        node.code_hash,
                        version,
                        namespace=namespace,
                    )
                except Exception:
                    queue_create_error_total.inc()
                    queue_create_error_total._val = queue_create_error_total._value.get()  # type: ignore[attr-defined]
                    raise
            return namespaced
        for n in nodes:
            rec = existing.get(n.node_id)
            node_compute_key = n.compute_key or compute_key(
                n.node_id,
                world_id=compute_context.world_id or None,
                execution_domain=compute_context.execution_domain or None,
                as_of=compute_context.as_of or None,
                partition=compute_context.partition or None,
                dataset_fingerprint=compute_context.dataset_fingerprint or None,
            )
            n.compute_key = node_compute_key
            key = partition_key(
                n.node_id,
                n.interval,
                n.bucket,
                compute_key=node_compute_key,
            )
            bindings = self._bindings.setdefault(n.node_id, {})
            cached = bindings.get(node_compute_key)
            if cached and cached.code_hash == n.code_hash:
                topic = _ensure_topic_namespace(cached.topic, n)
                cached.topic = topic
                queue_map[key] = topic
                if cached.schema_hash != n.schema_hash:
                    buffering_nodes.append(n)
                continue
            if rec and rec.code_hash == n.code_hash and not bindings:
                topic = _ensure_topic_namespace(rec.topic, n)
                queue_map[key] = topic
                bindings[node_compute_key] = _CachedBinding(
                    topic=topic,
                    code_hash=rec.code_hash,
                    schema_hash=rec.schema_hash,
                )
                if rec.schema_hash != n.schema_hash:
                    buffering_nodes.append(n)
                continue
            if rec and rec.code_hash == n.code_hash and node_compute_key not in bindings:
                self._record_cross_context_hit(n, compute_context)
                if rec.schema_hash != n.schema_hash:
                    buffering_nodes.append(n)
            try:
                topic = self.queue_manager.upsert(
                    _asset_from_tags(n.tags),
                    n.node_type,
                    n.code_hash,
                    version,
                    namespace=namespace,
                )
            except Exception:
                queue_create_error_total.inc()
                queue_create_error_total._val = queue_create_error_total._value.get()  # type: ignore[attr-defined]
                raise
            topic = _ensure_topic_namespace(topic, n)
            queue_map[key] = topic
            new_nodes.append(n)
            bindings[node_compute_key] = _CachedBinding(
                topic=topic,
                code_hash=n.code_hash,
                schema_hash=n.schema_hash,
            )
        return queue_map, new_nodes, buffering_nodes

    def _buffer_instructions(self, nodes: Iterable[NodeInfo]) -> List[BufferInstruction]:
        """Create buffering instructions with lag equal to ``period``."""
        result: List[BufferInstruction] = []
        for n in nodes:
            lag = n.period or 0
            self.node_repo.mark_buffering(n.node_id, compute_key=n.compute_key)
            instruction = BufferInstruction(
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
            instruction.compute_key = n.compute_key
            result.append(instruction)
        return result

    # Step 4 ---------------------------------------------------------------
    def _insert_sentinel(
        self, sentinel_id: str, nodes: Iterable[NodeInfo], version: str
    ) -> None:
        self.node_repo.insert_sentinel(
            sentinel_id, [n.node_id for n in nodes], version
        )

    # Step 5 is handled inside _hash_compare via queue upsert --------------

    # Step 6 ---------------------------------------------------------------
    def _stream_send(
        self,
        queue_map: Dict[str, str],
        sentinel_id: str,
        version: str,
        new_nodes: List[NodeInfo],
        buffering_nodes: List[BufferInstruction],
    ) -> None:
        CHUNK_SIZE = 100
        total = max(len(new_nodes), len(buffering_nodes))

        def await_ack() -> None:
            MAX_RETRY = 3
            for _ in range(MAX_RETRY):
                status = self.stream_sender.wait_for_ack()
                if status is AckStatus.OK:
                    return
                resume = getattr(self.stream_sender, "resume_from_last_offset", None)
                if callable(resume):
                    resume()
            raise TimeoutError("Client did not acknowledge diff chunk")

        if total == 0:
            # 그래도 최소 1개는 보내야 함 (empty chunk)
            self.stream_sender.send(
                DiffChunk(
                    queue_map=queue_map,
                    sentinel_id=sentinel_id,
                    version=version,
                    new_nodes=[],
                    buffering_nodes=[],
                )
            )
            await_ack()
            return

        for i in range(0, total, CHUNK_SIZE):
            chunk_new = new_nodes[i:i+CHUNK_SIZE]
            chunk_buf = buffering_nodes[i:i+CHUNK_SIZE]
            self.stream_sender.send(
                DiffChunk(
                    queue_map=queue_map,
                    sentinel_id=sentinel_id,
                    version=version,
                    new_nodes=chunk_new,
                    buffering_nodes=chunk_buf,
                )
            )
            await_ack()

    def diff(self, request: DiffRequest) -> DiffChunk:
        start = time.perf_counter()
        try:
            nodes, version, inferred_context, namespace = self._pre_scan(
                request.dag_json
            )
            merged_context = replace(
                inferred_context,
                world_id=_stringify(request.world_id) or inferred_context.world_id,
                execution_domain=_normalize_execution_domain(
                    request.execution_domain or inferred_context.execution_domain
                ),
                as_of=_stringify(request.as_of) or inferred_context.as_of,
                partition=_stringify(request.partition) or inferred_context.partition,
                dataset_fingerprint=
                _stringify(request.dataset_fingerprint)
                or inferred_context.dataset_fingerprint,
            )
            existing = self._db_fetch([n.node_id for n in nodes])
            queue_map, new_nodes, buffering = self._hash_compare(
                nodes,
                existing,
                version,
                merged_context,
                namespace=namespace,
            )
            instructions = self._buffer_instructions(buffering)
            sentinel_id = f"{request.strategy_id}-sentinel"
            self._insert_sentinel(sentinel_id, new_nodes, version)
            if not new_nodes:
                sentinel_gap_count.inc()
                sentinel_gap_count._val = sentinel_gap_count._value.get()  # type: ignore[attr-defined]
            self._stream_send(queue_map, sentinel_id, version, new_nodes, instructions)
            # success path accounted as processed request
            diff_requests_total.inc()
            return DiffChunk(
                queue_map=queue_map,
                sentinel_id=sentinel_id,
                version=version,
                new_nodes=new_nodes,
                buffering_nodes=instructions,
            )
        except Exception:
            # record failure for alerting, then propagate
            diff_failures_total.inc()
            raise
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
            "c.schema_id AS schema_id, q.topic AS topic, "
            "q.interval AS interval, c.period AS period, c.tags AS tags"
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
                    schema_id=r.get("schema_id"),
                    interval=r.get("interval"),
                    period=r.get("period"),
                    tags=list(r.get("tags", [])),
                    topic=r.get("topic"),
                    is_global=r.get("global", False),
                )
            return records

    def insert_sentinel(
        self,
        sentinel_id: str,
        node_ids: Iterable[str],
        version: str,
        *,
        breaker: AsyncCircuitBreaker | None = None,
    ) -> None:
        if not node_ids:
            return
        query = (
            "CREATE (s:VersionSentinel {sentinel_id: $sid, version: $version, "
            "created_at: timestamp()}) "
            "WITH s UNWIND $ids AS nid MATCH (c:ComputeNode {node_id: nid}) "
            "MERGE (s)-[:HAS]->(c)"
        )
        with self._open_session(breaker) as session:
            session.run(
                query,
                sid=sentinel_id,
                version=version,
                ids=list(node_ids),
            )

    def get_queues_by_tag(
        self,
        tags: Iterable[str],
        interval: int,
        match_mode: str = "any",
        *,
        breaker: AsyncCircuitBreaker | None = None,
    ) -> list[dict[str, object]]:
        if not tags:
            return []
        if match_mode == "all":
            cond = "all(t IN $tags WHERE t IN c.tags)"
        else:
            cond = "any(t IN c.tags WHERE t IN $tags)"
        query = (
            "MATCH (c:ComputeNode)-[:EMITS]->(q:Queue) "
            f"WHERE {cond} AND q.interval = $interval "
            "RETURN q.topic AS topic, c.global AS global"
        )
        with self._open_session(breaker) as session:
            result = session.run(query, tags=list(tags), interval=interval)
            return [
                {"queue": r.get("topic"), "global": bool(r.get("global", False))}
                for r in result
            ]

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
            "c.schema_id AS schema_id, q.topic AS topic, q.interval AS interval, "
            "c.period AS period, c.tags AS tags "
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
                schema_id=record.get("schema_id"),
                interval=record.get("interval"),
                period=record.get("period"),
                tags=list(record.get("tags", [])),
                topic=record.get("topic"),
                is_global=record.get("global", False),
            )

    # buffering -------------------------------------------------------------

    def mark_buffering(
        self,
        node_id: str,
        *,
        compute_key: str | None = None,
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
        compute_key: str | None = None,
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
        compute_key: str | None = None,
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
        namespace: object | None = None,
    ) -> str:
        existing = self.admin.client.list_topics().keys()
        # Choose TopicConfig by topic type per spec. Default to 'indicator'.
        topic_type = "indicator"
        nt = (node_type or "").lower()
        if any(k in nt for k in ("exec", "trade", "order", "portfolio")):
            topic_type = "trade_exec"
        elif any(k in nt for k in ("raw", "price", "ohlcv")):
            topic_type = "raw"
        try:
            applied_cfg = get_config(topic_type)
        except Exception:
            applied_cfg = self.config
        topic = topic_name(
            asset,
            node_type,
            code_hash,
            version,
            dry_run=dry_run,
            existing=existing,
            namespace=namespace,
        )
        self.admin.create_topic_if_needed(topic, applied_cfg or self.config)
        return topic
