from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Dict, Iterable, List, MutableMapping, TYPE_CHECKING, Mapping
import math
from queue import Empty, Queue

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
    diff_requests_total,
    diff_failures_total,
    cross_context_cache_violation_total,
    set_active_version_weight,
)
from .models import (
    BufferInstruction,
    DiffChunk,
    DiffRequest,
    NodeInfo,
    NodeRecord,
)
from .normalize import (
    normalize_execution_domain,
    normalize_version,
    stringify,
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
from qmtl.foundation.common import AsyncCircuitBreaker, crc32_of_list
from qmtl.foundation.common.compute_context import ComputeContext, coerce_compute_context
from qmtl.foundation.common.metrics_shared import observe_cross_context_cache_hit
from .monitor import AckStatus
from .repository import NodeRepository

if TYPE_CHECKING:  # pragma: no cover - optional import for typing
    from neo4j import Driver
@dataclass
class _CachedBinding:
    topic: str
    code_hash: str
    schema_hash: str
    context: ComputeContext


@dataclass
class _SentinelWeightEvent:
    sentinel_id: str
    weight: float
    sentinel_version: str
    world_id: str | None


@dataclass
class _SentinelWeightCacheEntry:
    weight: float
    version_label: str


class CrossContextTopicReuseError(RuntimeError):
    """Raised when a node attempts to reuse a topic across compute domains."""

    def __init__(
        self,
        node_id: str,
        *,
        attempted_context: ComputeContext,
        existing_context: ComputeContext | None,
    ) -> None:
        self.node_id = node_id
        self.attempted_context = attempted_context
        self.existing_context = existing_context
        message = self._build_message(node_id, attempted_context, existing_context)
        super().__init__(message)

    @staticmethod
    def _format_context(context: ComputeContext | None) -> str:
        if context is None:
            return "<unknown>"
        world = context.world_id or "<unset>"
        domain = context.execution_domain or "<unset>"
        as_of = context.as_of or "<unset>"
        partition = context.partition or "<unset>"
        dataset = context.dataset_fingerprint or "<unset>"
        return (
            f"world={world}, domain={domain}, as_of={as_of}, "
            f"partition={partition}, dataset={dataset}"
        )

    @classmethod
    def _build_message(
        cls,
        node_id: str,
        attempted: ComputeContext,
        existing: ComputeContext | None,
    ) -> str:
        attempted_str = cls._format_context(attempted)
        existing_str = cls._format_context(existing)
        return (
            "Cross-context topic reuse detected for node "
            f"'{node_id}'. Attempted context: {attempted_str}. "
            f"Existing context: {existing_str}."
        )




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


@dataclass(frozen=True)
class _DiffPlan:
    queue_map: Mapping[str, str]
    sentinel_id: str
    version: str
    crc32: int
    new_nodes: List[NodeInfo]
    buffering_nodes: List[BufferInstruction]


@dataclass
class _TopicBindingPlanEntry:
    node: NodeInfo
    compute_key: str
    topic: str | None
    needs_new_queue: bool
    needs_buffering: bool
    bindings: Dict[str, _CachedBinding]
    compute_context: ComputeContext


class _ChunkStreamer:
    """Manage diff chunk streaming and acknowledgements."""

    def __init__(
        self,
        sender: StreamSender,
        *,
        chunk_size: int = 100,
        ack_window: int = 10,
        max_retry: int = 3,
        deadline_seconds: float = 30.0,
    ) -> None:
        self._sender = sender
        self._chunk_size = chunk_size
        self._ack_window = ack_window
        self._max_retry = max_retry
        self._deadline_seconds = deadline_seconds
        self._outstanding = 0

    def stream(
        self,
        queue_map: Mapping[str, str],
        sentinel_id: str,
        version: str,
        new_nodes: List[NodeInfo],
        buffering_nodes: List[BufferInstruction],
        crc32: int,
    ) -> None:
        total = max(len(new_nodes), len(buffering_nodes))

        if total == 0:
            self._send_chunk(
                DiffChunk(
                    queue_map=queue_map,
                    sentinel_id=sentinel_id,
                    version=version,
                    crc32=crc32,
                    new_nodes=[],
                    buffering_nodes=[],
                )
            )
            self._drain_ack_window()
            return

        for offset in range(0, total, self._chunk_size):
            chunk_new = new_nodes[offset : offset + self._chunk_size]
            chunk_buffer = buffering_nodes[offset : offset + self._chunk_size]
            self._send_chunk(
                DiffChunk(
                    queue_map=queue_map,
                    sentinel_id=sentinel_id,
                    version=version,
                    crc32=crc32,
                    new_nodes=chunk_new,
                    buffering_nodes=chunk_buffer,
                )
            )
            if self._outstanding >= self._ack_window:
                self._await_ack()

        self._drain_ack_window()

    def _send_chunk(self, chunk: DiffChunk) -> None:
        self._sender.send(chunk)
        self._outstanding += 1

    def _drain_ack_window(self) -> None:
        while self._outstanding:
            self._await_ack()

    def _await_ack(self) -> None:
        deadline = time.monotonic() + self._deadline_seconds
        attempts = 0
        while True:
            status = self._sender.wait_for_ack()
            if status is AckStatus.OK:
                self._outstanding -= 1
                return
            resume = getattr(self._sender, "resume_from_last_offset", None)
            if callable(resume):
                resume()
            attempts += 1
            if attempts < self._max_retry:
                continue
            if time.monotonic() >= deadline:
                break
            attempts = 0
        raise TimeoutError("Client did not acknowledge diff chunk")


class DiffService:
    """Process :class:`DiffRequest` following the documented steps."""

    def __init__(
        self,
        node_repo: NodeRepository,
        queue_manager: QueueManager,
        stream_sender: StreamSender,
        *,
        sentinel_weights: MutableMapping[
            tuple[str, str], _SentinelWeightCacheEntry | float
        ]
        | None = None,
    ) -> None:
        self.node_repo = node_repo
        self.queue_manager = queue_manager
        self.stream_sender = stream_sender
        self._bindings: Dict[str, Dict[str, _CachedBinding]] = {}
        self._sentinel_weights: MutableMapping[
            tuple[str, str], _SentinelWeightCacheEntry | float
        ] = (
            sentinel_weights if sentinel_weights is not None else {}
        )
        self._weight_events: Queue[_SentinelWeightEvent] = Queue()

    @staticmethod
    def _coerce_weight(raw: object) -> float | None:
        """Convert ``raw`` to a bounded float in ``[0, 1]``."""

        if raw is None:
            return None
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return None
        if math.isnan(value) or math.isinf(value):
            return None
        if value < 0.0:
            value = 0.0
        elif value > 1.0:
            value = 1.0
        return value

    def consume_weight_events(self) -> list[_SentinelWeightEvent]:
        """Return sentinel weight events recorded during the last diff."""

        events: list[_SentinelWeightEvent] = []
        while True:
            try:
                events.append(self._weight_events.get_nowait())
            except Empty:
                break
        return events

    def _record_sentinel_weight(
        self,
        sentinel_id: str,
        sentinel_version: str,
        weight: float | None,
        *,
        world_id: str | None,
    ) -> None:
        """Store sentinel weight change and emit metrics when updated."""

        normalized = self._coerce_weight(weight)
        if normalized is None:
            return

        version_label = sentinel_version or sentinel_id
        set_active_version_weight(version_label, normalized)

        cache_key = (world_id or "", sentinel_id)
        prev_entry = self._sentinel_weights.get(cache_key)
        prev_weight: float | None = None
        prev_version: str | None = None
        if isinstance(prev_entry, _SentinelWeightCacheEntry):
            prev_weight = prev_entry.weight
            prev_version = prev_entry.version_label
        elif isinstance(prev_entry, (int, float)):
            prev_weight = float(prev_entry)
        if (
            prev_weight is not None
            and math.isclose(prev_weight, normalized, rel_tol=1e-6, abs_tol=1e-6)
            and prev_version == version_label
        ):
            return

        self._sentinel_weights[cache_key] = _SentinelWeightCacheEntry(
            weight=normalized,
            version_label=version_label,
        )
        self._weight_events.put(
            _SentinelWeightEvent(
                sentinel_id=sentinel_id,
                weight=normalized,
                sentinel_version=version_label,
                world_id=world_id,
            )
        )

    @staticmethod
    def _asset_from_tags(tags: list[str]) -> str:
        """Prefer a short, stable asset name derived from tags."""

        for tag in tags:
            if not tag:
                continue
            sanitized = "".join(
                ch for ch in str(tag).lower() if ch.isalnum() or ch in ("_", "-")
            )
            if sanitized:
                return sanitized
        return "asset"

    # Step 1 ---------------------------------------------------------------
    def _pre_scan(
        self, dag_json: str
    ) -> tuple[List[NodeInfo], str, ComputeContext, str | None, float | None]:
        """Parse DAG JSON and return nodes, version, compute context, namespace."""
        data = _json_loads(dag_json)

        raw_nodes = data.get("nodes", []) or []
        meta_obj = data.get("meta")
        meta = meta_obj if isinstance(meta_obj, dict) else {}
        context = self._extract_compute_context(data)
        namespace = self._resolve_namespace(meta, context)
        filtered_nodes, sentinel_version, sentinel_weight = (
            self._separate_sentinel_nodes(raw_nodes)
        )
        node_map = {n["node_id"]: n for n in filtered_nodes if "node_id" in n}
        ordered_ids = self._topologically_order_nodes(node_map)
        nodes = self._build_node_infos(ordered_ids, node_map, context)
        version = self._resolve_version_label(data, meta, sentinel_version)
        sentinel_weight = self._resolve_sentinel_weight(meta, sentinel_weight)
        return nodes, version, context, namespace, sentinel_weight

    def _resolve_namespace(
        self, meta: Mapping[str, Any], context: ComputeContext
    ) -> str | None:
        if not topic_namespace_enabled():
            return None
        raw_namespace = meta.get("topic_namespace")
        normalized = normalize_namespace(raw_namespace)
        if normalized:
            return normalized
        world_for_ns = context.world_id or stringify(meta.get("world") or meta.get("world_id"))
        domain_for_ns = context.execution_domain or normalize_execution_domain(
            meta.get("execution_domain") or meta.get("domain")
        )
        if world_for_ns:
            return build_namespace(world_for_ns, domain_for_ns)
        return None

    def _separate_sentinel_nodes(
        self, raw_nodes: Iterable[dict]
    ) -> tuple[list[dict], str | None, float | None]:
        sentinel_version: str | None = None
        sentinel_weight: float | None = None
        filtered: list[dict] = []
        for entry in raw_nodes:
            if not isinstance(entry, dict):
                continue
            if str(entry.get("node_type", "")) != "VersionSentinel":
                filtered.append(entry)
                continue
            sentinel_version = sentinel_version or self._extract_sentinel_version(entry)
            if sentinel_weight is None:
                sentinel_weight = self._extract_sentinel_weight(entry)
        return filtered, sentinel_version, sentinel_weight

    @staticmethod
    def _extract_sentinel_version(entry: Mapping[str, Any]) -> str | None:
        for key in ("version", "strategy_version", "build_version"):
            if key in entry:
                normalized = normalize_version(entry.get(key))
                if normalized:
                    return normalized
        return normalize_version(entry.get("node_id"))

    def _extract_sentinel_weight(self, entry: Mapping[str, Any]) -> float | None:
        for key in ("traffic_weight", "sentinel_weight", "weight"):
            if key in entry:
                weight = self._coerce_weight(entry.get(key))
                if weight is not None:
                    return weight
        return None

    def _topologically_order_nodes(self, node_map: Dict[str, dict]) -> List[str]:
        deps: Dict[str, set[str]] = {
            nid: set(node_map[nid].get("inputs", [])) for nid in node_map
        }
        ordered: List[str] = []
        ready = [nid for nid, incoming in deps.items() if not incoming]
        while ready:
            nid = ready.pop(0)
            ordered.append(nid)
            for other, incoming in deps.items():
                if nid in incoming:
                    incoming.remove(nid)
                    if not incoming:
                        ready.append(other)
        if len(ordered) != len(node_map):
            return list(node_map.keys())
        return ordered

    def _build_node_infos(
        self,
        ordered_ids: Iterable[str],
        node_map: Dict[str, dict],
        context: ComputeContext,
    ) -> List[NodeInfo]:
        nodes = [
            NodeInfo(
                node_id=node_map[node_id]["node_id"],
                node_type=node_map[node_id].get("node_type", ""),
                code_hash=node_map[node_id]["code_hash"],
                schema_hash=node_map[node_id]["schema_hash"],
                schema_id=node_map[node_id].get("schema_id", ""),
                interval=node_map[node_id].get("interval"),
                period=node_map[node_id].get("period"),
                tags=list(node_map[node_id].get("tags", [])),
                bucket=node_map[node_id].get("bucket"),
            )
            for node_id in ordered_ids
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
        return nodes

    @staticmethod
    def _resolve_version_label(
        data: Mapping[str, Any],
        meta: Mapping[str, Any],
        sentinel_version: str | None,
    ) -> str:
        if sentinel_version:
            return sentinel_version
        return normalize_version(
            data.get("strategy_version")
            or data.get("version")
            or meta.get("version")
            or meta.get("strategy_version")
            or meta.get("build_version")
        )

    def _resolve_sentinel_weight(
        self,
        meta: Mapping[str, Any],
        sentinel_weight: float | None,
    ) -> float | None:
        if sentinel_weight is not None:
            return sentinel_weight
        for key in ("traffic_weight", "sentinel_weight", "weight"):
            if key in meta:
                coerced = self._coerce_weight(meta.get(key))
                if coerced is not None:
                    return coerced
        return None

    # Step 2 ---------------------------------------------------------------
    def _db_fetch(self, node_ids: Iterable[str]) -> Dict[str, NodeRecord]:
        return self.node_repo.get_nodes(node_ids)

    def _extract_compute_context(self, payload: dict) -> ComputeContext:
        meta = payload.get("meta") or {}
        ctx = payload.get("compute_context")
        if not isinstance(ctx, dict):
            ctx = meta.get("compute_context") if isinstance(meta, dict) else None
        base = coerce_compute_context(ctx if isinstance(ctx, dict) else None)
        if isinstance(meta, dict):
            dataset = meta.get("dataset_fingerprint")
            if dataset and not base.dataset_fingerprint:
                base = base.with_overrides(dataset_fingerprint=dataset)
        return base

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
        world_label = context.world_id or "__unset__"
        domain_label = context.execution_domain or "__unset__"
        counter = cross_context_cache_violation_total.labels(
            node_id=str(node.node_id),
            world_id=str(world_label),
            execution_domain=str(domain_label),
        )
        counter.inc()
        key = (str(node.node_id), str(world_label), str(domain_label))
        cross_context_cache_violation_total._vals[key] = (  # type: ignore[attr-defined]
            cross_context_cache_violation_total._vals.get(key, 0) + 1  # type: ignore[attr-defined]
        )

    def _handle_cross_context_violation(
        self, node: NodeInfo, compute_context: ComputeContext, bindings: Dict[str, _CachedBinding]
    ) -> None:
        existing_binding = next(iter(bindings.values()), None)
        existing_context = existing_binding.context if existing_binding else None
        self._record_cross_context_hit(node, compute_context)
        raise CrossContextTopicReuseError(
            node.node_id,
            attempted_context=compute_context,
            existing_context=existing_context,
        )

    def _ensure_compute_key(
        self, node: NodeInfo, compute_context: ComputeContext
    ) -> str:
        if node.compute_key:
            return node.compute_key
        node.compute_key = compute_key(
            node.node_id,
            world_id=compute_context.world_id or None,
            execution_domain=compute_context.execution_domain or None,
            as_of=compute_context.as_of or None,
            partition=compute_context.partition or None,
            dataset_fingerprint=compute_context.dataset_fingerprint or None,
        )
        return node.compute_key

    def _partition_key_for(self, node: NodeInfo, compute_key_value: str) -> str:
        return partition_key(
            node.node_id,
            node.interval,
            node.bucket,
            compute_key=compute_key_value,
        )

    def _upsert_topic(
        self, node: NodeInfo, version: str, namespace: object | None
    ) -> str:
        try:
            return self.queue_manager.upsert(
                self._asset_from_tags(node.tags),
                node.node_type,
                node.code_hash,
                version,
                namespace=namespace,
            )
        except Exception:
            queue_create_error_total.inc()
            queue_create_error_total._val = queue_create_error_total._value.get()  # type: ignore[attr-defined]
            raise

    def _apply_namespace(
        self, topic: str, node: NodeInfo, version: str, namespace: object | None
    ) -> str:
        if not namespace:
            return topic
        namespaced = ensure_namespace(topic, namespace)
        if namespaced == topic:
            return topic
        return self._upsert_topic(node, version, namespace)

    def _build_topic_binding_plan(
        self,
        nodes: Iterable[NodeInfo],
        existing: Dict[str, NodeRecord],
        compute_context: ComputeContext,
    ) -> list[_TopicBindingPlanEntry]:
        plan: list[_TopicBindingPlanEntry] = []
        for node in nodes:
            bindings = self._bindings.setdefault(node.node_id, {})
            compute_key_value = self._ensure_compute_key(node, compute_context)
            cached = bindings.get(compute_key_value)
            record = existing.get(node.node_id)

            if cached and cached.code_hash == node.code_hash:
                plan.append(
                    _TopicBindingPlanEntry(
                        node=node,
                        compute_key=compute_key_value,
                        topic=cached.topic,
                        needs_new_queue=False,
                        needs_buffering=cached.schema_hash != node.schema_hash,
                        bindings=bindings,
                        compute_context=compute_context,
                    )
                )
                continue

            if record and record.code_hash == node.code_hash:
                if bindings and compute_key_value not in bindings:
                    self._handle_cross_context_violation(node, compute_context, bindings)
                bindings[compute_key_value] = _CachedBinding(
                    topic=record.topic,
                    code_hash=record.code_hash,
                    schema_hash=record.schema_hash,
                    context=compute_context,
                )
                plan.append(
                    _TopicBindingPlanEntry(
                        node=node,
                        compute_key=compute_key_value,
                        topic=record.topic,
                        needs_new_queue=False,
                        needs_buffering=record.schema_hash != node.schema_hash,
                        bindings=bindings,
                        compute_context=compute_context,
                    )
                )
                continue

            plan.append(
                _TopicBindingPlanEntry(
                    node=node,
                    compute_key=compute_key_value,
                    topic=None,
                    needs_new_queue=True,
                    needs_buffering=False,
                    bindings=bindings,
                    compute_context=compute_context,
                )
            )

        return plan

    def _execute_topic_binding_plan(
        self,
        plan: Iterable[_TopicBindingPlanEntry],
        *,
        version: str,
        namespace: object | None,
    ) -> tuple[Dict[str, str], List[NodeInfo], List[NodeInfo]]:
        queue_map: Dict[str, str] = {}
        new_nodes: List[NodeInfo] = []
        buffering_nodes: List[NodeInfo] = []

        for entry in plan:
            topic = entry.topic
            if entry.needs_new_queue:
                topic = self._upsert_topic(entry.node, version, namespace)
                new_nodes.append(entry.node)
            if topic is None:
                continue
            topic = self._apply_namespace(topic, entry.node, version, namespace)
            entry.bindings[entry.compute_key] = _CachedBinding(
                topic=topic,
                code_hash=entry.node.code_hash,
                schema_hash=entry.node.schema_hash,
                context=entry.compute_context,
            )

            key = self._partition_key_for(entry.node, entry.compute_key)
            queue_map[key] = topic
            if entry.needs_buffering:
                buffering_nodes.append(entry.node)

        return queue_map, new_nodes, buffering_nodes


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
        plan = self._build_topic_binding_plan(nodes, existing, compute_context)
        return self._execute_topic_binding_plan(
            plan, version=version, namespace=namespace
        )

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
        crc32: int,
    ) -> None:
        streamer = _ChunkStreamer(self.stream_sender)
        streamer.stream(
            queue_map,
            sentinel_id,
            version,
            new_nodes,
            buffering_nodes,
            crc32,
        )

    def diff(self, request: DiffRequest) -> DiffChunk:
        start = time.perf_counter()
        try:
            plan = self._prepare_diff(request)
            self._stream_send(
                plan.queue_map,
                plan.sentinel_id,
                plan.version,
                plan.new_nodes,
                plan.buffering_nodes,
                plan.crc32,
            )
            diff_requests_total.inc()
            return self._build_chunk(plan)
        except Exception:
            diff_failures_total.inc()
            raise
        finally:
            duration_ms = (time.perf_counter() - start) * 1000
            observe_diff_duration(duration_ms)

    async def diff_async(self, request: DiffRequest) -> DiffChunk:
        return await asyncio.to_thread(self.diff, request)

    def _prepare_diff(self, request: DiffRequest) -> _DiffPlan:
        nodes, version, inferred_context, namespace, sentinel_weight = self._pre_scan(
            request.dag_json
        )
        merged_context = self._merge_context(inferred_context, request)
        existing = self._db_fetch([n.node_id for n in nodes])
        queue_map, new_nodes, buffering = self._hash_compare(
            nodes,
            existing,
            version,
            merged_context,
            namespace=namespace,
        )
        instructions = self._buffer_instructions(buffering)
        sentinel_id = self._build_sentinel_id(request.strategy_id)
        self._insert_sentinel(sentinel_id, new_nodes, version)
        if not new_nodes:
            sentinel_gap_count.inc()
            sentinel_gap_count._val = sentinel_gap_count._value.get()  # type: ignore[attr-defined]
        crc32 = crc32_of_list(n.node_id for n in nodes)
        self._record_sentinel_weight(
            sentinel_id,
            version,
            sentinel_weight,
            world_id=merged_context.world_id or None,
        )
        return _DiffPlan(
            queue_map=queue_map,
            sentinel_id=sentinel_id,
            version=version,
            crc32=crc32,
            new_nodes=new_nodes,
            buffering_nodes=instructions,
        )

    def _merge_context(
        self, inferred_context: ComputeContext, request: DiffRequest
    ) -> ComputeContext:
        return replace(
            inferred_context,
            world_id=stringify(request.world_id) or inferred_context.world_id,
            execution_domain=normalize_execution_domain(
                request.execution_domain or inferred_context.execution_domain
            ),
            as_of=stringify(request.as_of) or inferred_context.as_of,
            partition=stringify(request.partition) or inferred_context.partition,
            dataset_fingerprint=
            stringify(request.dataset_fingerprint)
            or inferred_context.dataset_fingerprint,
        )

    @staticmethod
    def _build_sentinel_id(strategy_id: str) -> str:
        return f"{strategy_id}-sentinel"

    @staticmethod
    def _build_chunk(plan: _DiffPlan) -> DiffChunk:
        return DiffChunk(
            queue_map=plan.queue_map,
            sentinel_id=plan.sentinel_id,
            version=plan.version,
            crc32=plan.crc32,
            new_nodes=plan.new_nodes,
            buffering_nodes=plan.buffering_nodes,
        )


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
