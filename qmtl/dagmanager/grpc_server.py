from __future__ import annotations

from typing import AsyncIterable, Dict
import asyncio
import threading
from collections import deque

import grpc

from opentelemetry.instrumentation.grpc import aio_server_interceptor

from .diff_service import (
    DiffService,
    DiffRequest,
    StreamSender,
    DiffChunk,
    NodeRepository,
    QueueManager,
)
from .monitor import AckStatus
from .kafka_admin import KafkaAdmin
from qmtl.common import AsyncCircuitBreaker
from .callbacks import post_with_backoff
from ..common.cloudevents import format_event
from .garbage_collector import GarbageCollector
from .controlbus_producer import ControlBusProducer
from ..proto import dagmanager_pb2, dagmanager_pb2_grpc
from .dagmanager_health import get_health


class _GrpcStream(StreamSender):
    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop
        self.queue: asyncio.Queue[DiffChunk | None] = asyncio.Queue()
        self._ack = threading.Event()
        self._last_ack = AckStatus.OK
        self._pending: deque[DiffChunk] = deque()

    def send(self, chunk: DiffChunk) -> None:
        self._pending.append(chunk)
        asyncio.run_coroutine_threadsafe(self.queue.put(chunk), self.loop)

    def wait_for_ack(self) -> AckStatus:
        if self._ack.wait(timeout=1.0):
            self._ack.clear()
            return self._last_ack
        self._last_ack = AckStatus.TIMEOUT
        return self._last_ack

    def ack(self, status: AckStatus = AckStatus.OK) -> None:
        if self._pending:
            self._pending.popleft()
        self._last_ack = status
        self._ack.set()

    def ack_status(self) -> AckStatus:
        return self._last_ack

    def resume_from_last_offset(self) -> None:
        if not self._pending:
            self._last_ack = AckStatus.OK
            return
        for chunk in list(self._pending):
            asyncio.run_coroutine_threadsafe(self.queue.put(chunk), self.loop)
        self._last_ack = AckStatus.OK


class DiffServiceServicer(dagmanager_pb2_grpc.DiffServiceServicer):
    def __init__(
        self,
        service: DiffService,
        callback_url: str | None = None,
        bus: ControlBusProducer | None = None,
    ) -> None:
        self._service = service
        self._callback_url = callback_url
        self._bus = bus
        self._streams: Dict[str, _GrpcStream] = {}

    async def Diff(
        self,
        request: dagmanager_pb2.DiffRequest,
        context: grpc.aio.ServicerContext,
    ) -> AsyncIterable[dagmanager_pb2.DiffChunk]:
        sentinel_id = f"{request.strategy_id}-sentinel"
        stream = _GrpcStream(asyncio.get_running_loop())
        self._streams[sentinel_id] = stream
        svc = DiffService(self._service.node_repo, self._service.queue_manager, stream)
        fut = asyncio.create_task(
            svc.diff_async(DiffRequest(strategy_id=request.strategy_id, dag_json=request.dag_json))
        )
        fut.add_done_callback(lambda _fut: stream.queue.put_nowait(None))
        try:
            while True:
                chunk = await stream.queue.get()
                if chunk is None:
                    break
                pb = dagmanager_pb2.DiffChunk(
                    queue_map=chunk.queue_map,
                    sentinel_id=chunk.sentinel_id,
                    buffer_nodes=[
                            dagmanager_pb2.BufferInstruction(
                                node_id=n.node_id,
                                node_type=n.node_type,
                                code_hash=n.code_hash,
                                schema_hash=n.schema_hash,
                                schema_id=n.schema_id,
                                interval=n.interval or 0,
                                period=n.period or 0,
                                tags=list(n.tags),
                                lag=n.lag,
                            )
                        for n in getattr(chunk, 'buffering_nodes', [])
                    ],
                )
                if getattr(chunk, 'new_nodes', None):
                    callbacks = []
                    for node in chunk.new_nodes:
                        if node.tags and node.interval is not None:
                            payload = {
                                "tags": node.tags,
                                "interval": node.interval,
                                "queues": [chunk.queue_map.get(node.node_id, "")],
                                "match_mode": "any",
                            }
                            event = format_event(
                                "qmtl.dagmanager", "queue_update", payload
                            )
                            if self._callback_url:
                                callbacks.append(
                                    post_with_backoff(self._callback_url, event)
                                )
                            if self._bus:
                                await self._bus.publish_queue_update(
                                    payload["tags"],
                                    payload["interval"],
                                    payload["queues"],
                                    payload["match_mode"],
                                )
                    if callbacks:
                        await asyncio.gather(*callbacks)
                yield pb
        finally:
            fut.cancel()
            await fut
            self._streams.pop(sentinel_id, None)

    async def AckChunk(
        self,
        request: dagmanager_pb2.ChunkAck,
        context: grpc.aio.ServicerContext,
    ) -> dagmanager_pb2.ChunkAck:
        stream = self._streams.get(request.sentinel_id)
        if stream is not None:
            stream.ack()
        return dagmanager_pb2.ChunkAck(
            sentinel_id=request.sentinel_id, chunk_id=request.chunk_id
        )


class AdminServiceServicer(dagmanager_pb2_grpc.AdminServiceServicer):
    def __init__(
        self,
        gc: GarbageCollector | None = None,
        admin: KafkaAdmin | None = None,
        repo: NodeRepository | None = None,
        diff: DiffService | None = None,
        callback_url: str | None = None,
        bus: ControlBusProducer | None = None,
    ) -> None:
        self._gc = gc
        self._admin = admin
        self._repo = repo
        self._diff = diff
        self._callback_url = callback_url
        self._bus = bus

    async def Cleanup(
        self,
        request: dagmanager_pb2.CleanupRequest,
        context: grpc.aio.ServicerContext,
    ) -> dagmanager_pb2.CleanupResponse:
        if self._gc is not None:
            processed = self._gc.collect()
            if self._callback_url or self._bus:
                for qi in processed:
                    if getattr(qi, "interval", None) is not None:
                        payload = {
                            "tags": [qi.tag],
                            "interval": qi.interval,
                            "queues": [qi.name],
                            "match_mode": "any",
                        }
                        event = format_event(
                            "qmtl.dagmanager", "queue_update", payload
                        )
                        if self._callback_url:
                            await post_with_backoff(self._callback_url, event)
                        if self._bus:
                            await self._bus.publish_queue_update(
                                payload["tags"],
                                payload["interval"],
                                payload["queues"],
                                payload["match_mode"],
                            )
        return dagmanager_pb2.CleanupResponse()

    async def GetQueueStats(
        self,
        request: dagmanager_pb2.QueueStatsRequest,
        context: grpc.aio.ServicerContext,
    ) -> dagmanager_pb2.QueueStats:
        sizes = {}
        if self._admin is not None:
            sizes = self._admin.get_topic_sizes()
        if request.filter and self._repo is not None and sizes:
            tags: list[str] = []
            interval = 0
            try:
                parts = [p for p in request.filter.split(";") if p]
                kv = dict(p.split("=", 1) for p in parts if "=" in p)
                tag_str = kv.get("tag")
                if tag_str:
                    tags = tag_str.split(",")
                if "interval" in kv:
                    interval = int(kv["interval"])
            except Exception:
                tags = []
            if tags and interval:
                queues = set(
                    self._repo.get_queues_by_tag(tags, interval, match_mode="any")
                )
                sizes = {k: v for k, v in sizes.items() if k in queues}
        return dagmanager_pb2.QueueStats(sizes=sizes)

    async def RedoDiff(
        self,
        request: dagmanager_pb2.RedoDiffRequest,
        context: grpc.aio.ServicerContext,
    ) -> dagmanager_pb2.DiffResult:
        if self._diff is None:
            return dagmanager_pb2.DiffResult()
        chunk = self._diff.diff(
            DiffRequest(strategy_id=request.sentinel_id, dag_json=request.dag_json)
        )
        return dagmanager_pb2.DiffResult(
            queue_map=chunk.queue_map, sentinel_id=chunk.sentinel_id
        )


class TagQueryServicer(dagmanager_pb2_grpc.TagQueryServicer):
    def __init__(self, repo: NodeRepository) -> None:
        self._repo = repo

    async def GetQueues(
        self,
        request: dagmanager_pb2.TagQueryRequest,
        context: grpc.aio.ServicerContext,
    ) -> dagmanager_pb2.TagQueryReply:
        queues = self._repo.get_queues_by_tag(
            request.tags, request.interval, match_mode=request.match_mode or "any"
        )
        return dagmanager_pb2.TagQueryReply(queues=queues)


class HealthServicer(dagmanager_pb2_grpc.HealthCheckServicer):
    def __init__(self, driver) -> None:
        self._driver = driver

    async def Status(
        self,
        request: dagmanager_pb2.StatusRequest,
        context: grpc.aio.ServicerContext,
    ) -> dagmanager_pb2.StatusReply:
        info = get_health(self._driver)
        return dagmanager_pb2.StatusReply(
            neo4j=info.get("neo4j", "unknown"),
            state=info.get("dagmanager", "unknown"),
        )


def serve(
    neo4j_driver,
    kafka_admin_client,
    stream_sender: StreamSender,
    *,
    host: str = "0.0.0.0",
    port: int = 50051,
    callback_url: str | None = None,
    gc: GarbageCollector | None = None,
    repo: NodeRepository | None = None,
    queue: QueueManager | None = None,
    bus: ControlBusProducer | None = None,
) -> tuple[grpc.aio.Server, int]:
    admin = None
    if kafka_admin_client is not None:
        # Breaker uses manual reset; callers must reset after successful ops
        breaker = AsyncCircuitBreaker()
        admin = KafkaAdmin(kafka_admin_client, breaker=breaker)
    if repo is None:
        from .diff_service import Neo4jNodeRepository

        repo = Neo4jNodeRepository(neo4j_driver)
    if queue is None and admin is not None:
        from .diff_service import KafkaQueueManager

        queue = KafkaQueueManager(admin)
    diff_service = DiffService(repo, queue, stream_sender)

    try:
        server = grpc.aio.server(interceptors=(aio_server_interceptor(),))
    except TypeError:
        server = grpc.aio.server()
    dagmanager_pb2_grpc.add_DiffServiceServicer_to_server(
        DiffServiceServicer(diff_service, callback_url, bus), server
    )
    dagmanager_pb2_grpc.add_TagQueryServicer_to_server(
        TagQueryServicer(repo), server
    )
    dagmanager_pb2_grpc.add_AdminServiceServicer_to_server(
        AdminServiceServicer(
            gc, admin, repo, diff=diff_service, callback_url=callback_url, bus=bus
        ),
        server,
    )
    dagmanager_pb2_grpc.add_HealthCheckServicer_to_server(
        HealthServicer(neo4j_driver), server
    )
    bound_port = server.add_insecure_port(f"{host}:{port}")
    return server, bound_port
